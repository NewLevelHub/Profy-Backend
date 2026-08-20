# Incident: prod nginx crash-loop + prod domain routed to dev

Дата: 2026-08-03

## Что случилось

`profi_nginx_prod` ушёл в crash-loop (`Restarting`) на сервере. Логи:

```
2026/08/03 09:48:11 [emerg] 1#1: host not found in upstream "profy_frontend_prod:80" in /etc/nginx/nginx.conf:17
```

**Причина:** в `nginx.conf` был статический блок

```nginx
upstream frontend {
    server profy_frontend_prod:80;
}
```

`upstream {}` резолвит имя хоста **один раз при старте** nginx (в отличие от `proxy_pass $var` + `resolver`, который резолвит лениво на каждый запрос). Контейнера `profy_frontend_prod` на сервере не существует (`docker ps` его не показывал вообще) — поэтому nginx падал ещё до обработки первого запроса, и весь edge-nginx (обслуживающий и prod, и dev домены на одном контейнере) был недоступен.

Дополнительный контекст: ранее вручную редактировался `nginx.conf` на сервере, чтобы `profy.newlevelhub.kz` показывал контент из dev. При деплое (`git push` → `main` → `.github/workflows/cd.yml`) файл перезаписывается — CI копирует `nginx.prod.conf` из репозитория в `nginx.conf` на сервере (`cd.yml:102-105`). Это стёрло ручную правку и вернуло дефолтный prod-конфиг, который и запнулся об отсутствующий `profy_frontend_prod`.

## Что сделали (только на сервере, `~/profi-backend/nginx.conf`)

1. Убрали блок `upstream frontend { server profy_frontend_prod:80; }` целиком — он был единственной причиной краша.
2. В prod server-блоке (`server_name profy.newlevelhub.kz`, `listen 443 ssl`) заменили статический `proxy_pass` на ленивый resolve через dev-контейнеры — тем же паттерном, что уже использовался в dev server-блоке:

   - `location /api/`, `/docs`, `/openapi.json`:
     ```nginx
     set $api_dev_upstream http://profi_api_dev:8000;
     proxy_pass $api_dev_upstream;
     ```
   - `location /`:
     ```nginx
     set $frontend_dev_upstream http://profy_frontend_dev:80;
     proxy_pass $frontend_dev_upstream;
     ```

**Результат:** `profy.newlevelhub.kz` (prod URL) сейчас проксирует на **dev-контейнеры** (`profi_api_dev`, `profy_frontend_dev`), а не на prod (`profi_api_prod`, `profy_frontend_prod`). URL в адресной строке у пользователя — прод, контент — dev. Это осознанное решение (не побочный эффект фикса краша), которое уже было один раз сделано вручную ранее и потерялось при пуше.

## ⚠️ Важно на будущее

- Изменение **только на сервере**, в файл `nginx.prod.conf` в репозитории **не закоммичено**.
- При следующем `git push` в `main` (или ручном прогоне `cd.yml`) CI **снова перезапишет** `nginx.conf` из `nginx.prod.conf` и routing вернётся на prod-контейнеры (а если `profy_frontend_prod` к тому моменту так и не будет существовать — nginx **снова упадёт в crash-loop**).
- Если решение "prod-домен показывает dev" должно быть постоянным — нужно перенести те же правки в `nginx.prod.conf` в репозитории и запушить в `main`.
- Если это было временным (например, для демо) — не забыть, что откат произойдёт сам собой при следующем деплое, но краш вернётся вместе с ним, если `profy_frontend_prod` не поднят.
- Корневая нерешённая проблема: **контейнера `profy_frontend_prod` нет на сервере**. Пока это так, любой деплой с "чистым" `nginx.prod.conf` из репозитория будет ронять nginx. Это надо решить отдельно — либо задеплоить `profy_frontend_prod`, либо держать prod-домен указывающим на dev осознанно, либо (лучший вариант) сделать upstream `frontend` тоже lazy-resolve (`set` + `resolver`) в самом `nginx.prod.conf`, чтобы отсутствие одного контейнера не валило весь edge-nginx.

## Диагностические команды (на будущее)

```bash
# Логи причины краша
docker logs --tail 50 profi_nginx_prod

# Проверить синтаксис конфига без запуска прод-контейнера
docker run --rm --network profi-backend_profi_network \
  -v ~/profi-backend/nginx.conf:/etc/nginx/nginx.conf:ro \
  -v /etc/letsencrypt:/etc/letsencrypt:ro \
  nginx:alpine nginx -t

# Применить изменения к запущенному контейнеру (файл смонтирован как volume)
docker restart profi_nginx_prod
```
