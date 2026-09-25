# Agent rules

The backend supports Russian (`ru`) and Kazakh (`kk`). Any user-facing API detail, validation error, notification, or response text must come from the localization catalog.

Add matching keys and values to `app/i18n/catalog/` for both locales, preserve interpolation placeholders, and resolve text through the active request locale (`get_locale()`/`i18n_key()` without forcing a locale). Do not add hardcoded Russian, Kazakh, or English UI copy in routers, services, schemas, or handlers. Technical logs, identifiers, SQL, paths, and protocol values are not UI copy.

Run the relevant tests and syntax checks before finishing localization work.
