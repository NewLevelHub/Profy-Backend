"""Deployment regression checks, independent of the application and database."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


def read_yaml(path):
    # BaseLoader preserves GitHub's `on` key instead of treating it as a bool.
    return yaml.load((ROOT / path).read_text(), Loader=yaml.BaseLoader)


class DeploymentIsolationTests(unittest.TestCase):
    def test_only_branch_pushes_can_build_and_deploy(self):
        for file, branch in [("cd.yml", "main"), ("cd-dev.yml", "dev")]:
            workflow = read_yaml(f".github/workflows/{file}")
            self.assertEqual(workflow["on"], {"push": {"branches": [branch]}})
            self.assertEqual(workflow["concurrency"]["cancel-in-progress"], "false")
            for job in workflow["jobs"].values():
                self.assertEqual(job["if"], f"github.event_name == 'push' && github.ref == 'refs/heads/{branch}'")

    def test_dev_uploads_only_its_compose(self):
        job = read_yaml(".github/workflows/cd-dev.yml")["jobs"]["deploy_development"]
        copies = [s["with"] for s in job["steps"] if s.get("uses", "").startswith("appleboy/scp-action")]
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0]["source"], "docker-compose.dev.yml")
        self.assertEqual(copies[0]["target"], "${{ secrets.DEPLOY_PATH_DEV }}")

    def test_dev_script_never_mutates_production(self):
        job = read_yaml(".github/workflows/cd-dev.yml")["jobs"]["deploy_development"]
        step = next(s for s in job["steps"] if s.get("uses", "").startswith("appleboy/ssh-action"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / ".env.development").write_text(
                "POSTGRES_DB=dev_db\nPOSTGRES_USER=dev_user\nPOSTGRES_PASSWORD=test\nSECRET_KEY=test\nAPI_IMAGE=old\n"
            )
            (path / "docker").write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$COMMAND_LOG"\n')
            (path / "docker").chmod(0o755)
            env = dict(os.environ, PATH=f"{path}:{os.environ['PATH']}",
                       COMMAND_LOG=str(path / "commands"), DEPLOY_PATH=directory,
                       DOCKER_PASSWORD="test", DOCKER_USERNAME="test",
                       DOCKER_REGISTRY="registry.test", DOCKER_REPOSITORY="backend",
                       COMMIT_SHA="123456789abcdef",
                       API_IMAGE="registry.test/backend:sha-production")
            subprocess.run(["bash", "-eu", "-c", step["with"]["script"]], env=env,
                           check=True, capture_output=True, text=True)
            commands = (path / "commands").read_text().splitlines()
            self.assertIn("pull registry.test/test/backend:dev-sha-1234567", commands)
            self.assertTrue(any("api_dev" in command for command in commands))
            for command in commands:
                self.assertNotIn("prod", command)
                self.assertNotIn("nginx", command)
                self.assertFalse(command.startswith("run "))
                if command.startswith("compose "):
                    self.assertIn("--env-file .env.development -f docker-compose.dev.yml -p profy-dev ", command)
            saved_env = (path / ".env.development").read_text()
            self.assertIn("DEV_API_IMAGE=registry.test/test/backend:dev-sha-1234567", saved_env)
            self.assertNotIn("\nAPI_IMAGE=", saved_env)

    # `docker image ls` output as both deploy scripts request it
    # (CreatedAt|Repository|Tag), newest first is NOT assumed — the script sorts.
    IMAGE_FIXTURE = "\n".join([
        "2026-10-06 10:00:00 +0500 +05|test/backend|dev-sha-1234567",
        "2026-10-05 10:00:00 +0500 +05|test/backend|dev-sha-aaaaaaa",
        "2026-10-04 10:00:00 +0500 +05|test/backend|dev-sha-bbbbbbb",
        "2026-10-03 10:00:00 +0500 +05|registry.test/test/backend|dev-sha-ccccccc",
        "2026-10-02 10:00:00 +0500 +05|test/backend|dev-sha-0dd0dd0",
        "2026-10-06 11:00:00 +0500 +05|test/backend|sha-1234567",
        "2026-10-05 11:00:00 +0500 +05|test/backend|sha-eeeeeee",
        "2026-10-04 11:00:00 +0500 +05|test/backend|sha-fffffff",
        "2026-10-01 11:00:00 +0500 +05|test/backend|latest",
        "2026-10-01 11:00:00 +0500 +05|other/app|dev-sha-9999999",
        "2026-10-01 11:00:00 +0500 +05|other/app|sha-9999999",
        "2026-09-01 11:00:00 +0500 +05|postgres|16-alpine",
    ]) + "\n"

    def _run_deploy_script(self, workflow_file, job_name, env_file):
        job = read_yaml(f".github/workflows/{workflow_file}")["jobs"][job_name]
        step = next(s for s in job["steps"] if s.get("uses", "").startswith("appleboy/ssh-action"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / env_file).write_text(
                "POSTGRES_DB=db\nPOSTGRES_USER=user\nPOSTGRES_PASSWORD=test\nSECRET_KEY=test\n"
            )
            (path / "images").write_text(self.IMAGE_FIXTURE)
            # Fake docker: logs every call, serves the image list, and refuses to
            # remove the image a container still uses (like the real `rmi` without -f).
            (path / "docker").write_text(
                '#!/bin/bash\nprintf "%s\\n" "$*" >> "$COMMAND_LOG"\n'
                'if [ "$1 $2" = "image ls" ]; then cat "$IMAGE_FIXTURE"; fi\n'
                'if [ "$1" = "rmi" ] && [ "$2" = "$IN_USE_IMAGE" ]; then exit 1; fi\n'
            )
            (path / "docker").chmod(0o755)
            env = dict(os.environ, PATH=f"{path}:{os.environ['PATH']}",
                       COMMAND_LOG=str(path / "commands"), IMAGE_FIXTURE=str(path / "images"),
                       IN_USE_IMAGE="test/backend:dev-sha-0dd0dd0",
                       DEPLOY_PATH=directory, DOCKER_PASSWORD="test", DOCKER_USERNAME="test",
                       DOCKER_REGISTRY="registry.test", DOCKER_REPOSITORY="backend",
                       COMMIT_SHA="123456789abcdef")
            subprocess.run(["bash", "-eu", "-c", step["with"]["script"]], env=env,
                           check=True, capture_output=True, text=True)
            commands = (path / "commands").read_text().splitlines()
            return sorted(c.split(" ", 1)[1] for c in commands if c.startswith("rmi "))

    def test_dev_deploy_prunes_only_old_dev_images(self):
        removed = self._run_deploy_script("cd-dev.yml", "deploy_development", ".env.development")
        # Kept: the image just deployed (1234567) and the newest previous (aaaaaaa).
        # Attempted: older dev-sha images, incl. one still in use (0dd0dd0), which
        # the fake docker refuses — and the deploy must still succeed.
        self.assertEqual(removed, [
            "registry.test/test/backend:dev-sha-ccccccc",
            "test/backend:dev-sha-0dd0dd0",
            "test/backend:dev-sha-bbbbbbb",
        ])
        self.assertFalse(any(":sha-" in image or image.endswith(":latest") for image in removed))

    @unittest.skipUnless(shutil.which("flock"), "flock not installed")
    def test_prod_deploy_prunes_only_old_production_images(self):
        removed = self._run_deploy_script("cd.yml", "deploy_production", ".env.production")
        self.assertEqual(removed, ["test/backend:sha-fffffff"])

    def test_compose_separates_images_databases_and_media_writes(self):
        for file, service, prefix in [("prod", "api", "PROD"), ("dev", "api_dev", "DEV")]:
            config = read_yaml(f"docker-compose.{file}.yml")
            api = config["services"][service]
            self.assertTrue(api["image"].startswith("${" + prefix + "_API_IMAGE:?"))
            self.assertEqual(api["environment"]["DATABASE_URL"], "")
            self.assertEqual(api["environment"]["POSTGRES_HOST"], f"profi_db_{file}")
            self.assertEqual(api["environment"]["REDIS_URL"], f"redis://profi_redis_{file}:6379/0")
            if file == "dev":
                self.assertTrue(all(v.endswith(":ro") for v in api["volumes"]))
            else:
                self.assertNotIn("depends_on", config["services"]["nginx"])

    def test_prod_attaches_nginx_and_api_to_the_edge_network(self):
        config = read_yaml("docker-compose.prod.yml")
        self.assertEqual(config["networks"]["profi_edge"], {"external": "true", "name": "profi_edge"})
        for service in ("api", "nginx"):
            self.assertIn("profi_edge", config["services"][service]["networks"])
        # Data services never sit on the edge network.
        for service in ("db", "redis"):
            self.assertEqual(config["services"][service]["networks"], ["profi_network"])
        job = read_yaml(".github/workflows/cd.yml")["jobs"]["deploy_production"]
        script = next(s for s in job["steps"] if s.get("uses", "").startswith("appleboy/ssh-action"))["with"]["script"]
        create = "docker network inspect profi_edge >/dev/null 2>&1 || docker network create profi_edge"
        self.assertIn(create, script)
        self.assertLess(script.index(create), script.index("docker compose"))

    def test_dev_reaches_nginx_only_through_the_edge_network(self):
        config = read_yaml("docker-compose.dev.yml")
        self.assertEqual(config["networks"]["profi_edge"], {"external": "true", "name": "profi_edge"})
        self.assertEqual(config["services"]["api_dev"]["networks"], ["profi_network_dev", "profi_edge"])
        for service in ("db", "redis"):
            self.assertEqual(config["services"][service]["networks"], ["profi_network_dev"])
        # Never the production stack's own network (profi_db_prod / profi_redis_prod).
        names = {network.get("name") for network in config["networks"].values()}
        self.assertNotIn("profi-backend_profi_network", names)
        # Dev only checks that the edge network exists; creating it is production's job.
        workflow = (ROOT / ".github/workflows/cd-dev.yml").read_text()
        self.assertIn("docker network inspect profi_edge", workflow)
        self.assertNotIn("network create", workflow)

    def test_prod_routing_uses_explicit_production_container(self):
        nginx = (ROOT / "nginx.prod.conf").read_text()
        prod = nginx.split("# -- Dev:")[0]
        self.assertNotIn("proxy_pass http://api", prod)
        self.assertNotIn("http://profi_api_dev", prod)
        self.assertEqual(prod.count("set $api_prod_upstream http://profi_api_prod:8000;"), 3)

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI not installed")
    def test_compose_resolution_rejects_shared_image_and_overrides_wrong_database(self):
        for stage, service, prefix in [("prod", "api", "PROD"), ("dev", "api_dev", "DEV")]:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                shutil.copy(ROOT / f"docker-compose.{stage}.yml", path / "compose.yml")
                envfile = ".env.production" if stage == "prod" else ".env.development"
                (path / envfile).write_text(
                    "POSTGRES_DB=test_db\nPOSTGRES_USER=test_user\nPOSTGRES_PASSWORD=test\n"
                    "SECRET_KEY=test\nDATABASE_URL=postgresql://wrong-host/wrong-db\n"
                )
                env = {k: v for k, v in os.environ.items() if not k.startswith(("COMPOSE_", "DOCKER_", "POSTGRES_"))}
                for key in ("PROD_API_IMAGE", "DEV_API_IMAGE"):
                    env.pop(key, None)
                env["API_IMAGE"] = "registry.test/backend:wrong-shared-image"
                command = ["docker", "compose", "--env-file", envfile, "-f", "compose.yml", "config", "--format", "json"]
                missing = subprocess.run(command, cwd=path, env=env, capture_output=True, text=True)
                self.assertNotEqual(missing.returncode, 0)
                self.assertIn(f"{prefix}_API_IMAGE", missing.stderr)
                expected_image = f"registry.test/backend:{stage}-expected"
                env[f"{prefix}_API_IMAGE"] = expected_image
                result = subprocess.run(command, cwd=path, env=env, capture_output=True, text=True, check=True)
                api = json.loads(result.stdout)["services"][service]
                self.assertEqual(api["image"], expected_image)
                self.assertEqual(api["environment"]["DATABASE_URL"], "")
                self.assertEqual(api["environment"]["POSTGRES_HOST"], f"profi_db_{stage}")
                if stage == "dev":
                    self.assertTrue(api["volumes"][0]["read_only"])

    def test_shell_syntax(self):
        for file in ("cd.yml", "cd-dev.yml"):
            workflow = read_yaml(f".github/workflows/{file}")
            for job in workflow["jobs"].values():
                for step in job["steps"]:
                    script = step.get("run") or step.get("with", {}).get("script")
                    if script:
                        subprocess.run(["bash", "-n"], input=script, text=True, check=True)


if __name__ == "__main__":
    unittest.main()
