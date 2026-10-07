# Development keystore

`glucorag-dev.jks` is a **development-only** signing key, committed on purpose. It signs the
debug builds of both `:phone` and `:wear`, because the Wearable Data Layer only connects apps
that share the same package name and signing certificate. Never use it for a release build.

- alias: `glucorag`
- store and key password: `glucorag-dev`
- created with:

```
keytool -genkeypair -keystore android/keystore/glucorag-dev.jks -alias glucorag -keyalg RSA \
  -keysize 2048 -validity 10000 -storepass glucorag-dev -keypass glucorag-dev -dname "CN=GlucoRAG Dev"
```
