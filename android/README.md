# GlucoRAG phone and watch apps

**Research prototype. Not a medical device. Don't use it to make treatment decisions.** Your CGM
app's own alarms stay the safety net; GlucoRAG's alerts only add a forecast.

- **Phone app** (`phone/`, Android 9+): receives readings from Juggluco or xDrip+, uploads them to
  your GlucoRAG server, gets the forecast back, posts alerts, and sends the watch a snapshot.
- **Watch app** (`wear/`, Wear OS 3+; tested on Wear OS 6, which the Galaxy Watch4 Classic runs):
  two complications for your watch face ("Glucose now", "Next hour"), a tile, and an app. It never
  talks to the server; it shows what the phone sends.
- **Shared rules** (`shared/`): units, zones, trend, status wording, snapshot format, CGM broadcast
  parsing, upload thinning, and which server addresses may use plain HTTP.

Design: `../docs/superpowers/specs/2026-10-06-glucorag-wear-design.md`.

```mermaid
flowchart LR
  J[Juggluco / xDrip+] -->|broadcast| P[Phone app]
  P -->|readings, every ~5 min| S[GlucoRAG server]
  S -->|forecast, alerts| P
  P -->|snapshot| W[Watch]
  P -->|alert notification| W
```

## Build

Needs JDK 17 and the Android SDK (platform 37, build-tools 36). The Gradle wrapper downloads
Gradle 9.5.1.

```sh
cd android
export JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home   # any JDK 17
./gradlew :shared:testDebugUnitTest :phone:testDebugUnitTest :wear:testDebugUnitTest \
  :phone:lintDebug :wear:lintDebug :phone:assembleDebug :wear:assembleDebug
# APKs: phone/build/outputs/apk/debug/phone-debug.apk, wear/build/outputs/apk/debug/wear-debug.apk
```

Both apps are `org.glucorag.app` and are signed with the same key (`keystore/glucorag-dev.jks`,
development only). The watch and phone apps only talk to each other when the package name and the
signing key match, so always install a pair built from the same checkout.

## 1. Run the server on your home network

On the Mac, serve on all interfaces (the default only listens on 127.0.0.1):

```sh
source .venv/bin/activate
GLUCORAG_HOST=0.0.0.0 GLUCORAG_MODEL_PATH=models/shanghai-v1 \
GLUCORAG_SIM_REPORT=reports/sim/report.json glucorag-serve
```

Allow incoming connections when macOS asks. Find the Mac's address with
`ipconfig getifaddr en0` (for example `192.168.1.20`); the phone uses `http://192.168.1.20:8000`.

Create your account and profile on the website (`http://192.168.1.20:8000/ui/`) first: the forecast
needs your diabetes type, age, sex and BMI.

**Plain HTTP** is accepted only for home and Tailscale addresses (10.x, 172.16–31.x, 192.168.x,
169.254.x, loopback, 100.64–127.x, `*.local`, `*.ts.net`). Any other address must use `https://`,
so your token never travels unencrypted across the internet.

**Away from home** the phone can't reach the Mac: the watch still shows your current reading and
says "Forecast needs your GlucoRAG server"; readings wait on the phone and upload when you're back.
For forecasts anywhere, install [Tailscale](https://tailscale.com) on the Mac and phone and use the
Mac's Tailscale address, or `tailscale serve` for HTTPS (HTTPS names are published in public
certificate logs, so don't put personal details in the machine name).

## 2. Set up the phone

Install the phone app (`adb install phone-debug.apk`, with USB or wireless debugging on the phone).

1. **Connect:** enter the server address, tap **Check server** (it should say "Connected to
   GlucoRAG shanghai-v1"), then sign in.
2. **Where your readings come from:** GlucoRAG reads what Juggluco or xDrip+ share with other
   apps. If you only use the official Libre or Dexcom app, add one of them; both read the same
   sensors. Each only sends to apps you name:
   - **Juggluco:** Settings → **Glucodata broadcast** → tick `org.glucorag.app`.
   - **xDrip+:** Settings → Inter-app settings → **Broadcast locally** on, **Identify receiver**
     = `org.glucorag.app`, **Compatible Broadcast** on. Without Identify receiver, Android doesn't
     deliver xDrip+'s broadcast to other apps.

   The screen shows "Receiving: 142 mg/dL at 14:05" once readings arrive.
3. **Keep readings flowing:**
   - allow notifications;
   - Samsung: add GlucoRAG to **Never sleeping apps** (the button opens the list), and set the
     app's battery use to **Unrestricted**. Sleeping apps lose background work, so uploads stop;
   - Galaxy Wearable → Notifications → App notifications: make sure GlucoRAG is on, and turn on
     **Show while using phone** so alerts reach the watch while you use the phone. **Send test
     alert** checks it.

Readings upload about every 5 minutes (one per 5 minutes is enough for the 15-minute model).
Alerts buzz for a predicted low or high of medium or high severity, once per alert, and only while
the reading they came from is at most 15 minutes old.

## 3. Install the watch app (Galaxy Watch4 Classic)

1. On the watch: Settings → About watch → Software information → tap **Software version** 5 times
   to enable Developer options.
2. Settings → Developer options: turn on **ADB debugging**, turn **off automatic Wi-Fi** (or the
   watch drops Wi-Fi while connected to the phone), then **Wireless debugging** → **Pair new
   device**. The watch and Mac must be on the same Wi-Fi.
3. On the Mac (adb 30 or later):
   ```sh
   adb pair <watch-ip>:<pairing-port>      # enter the pairing code shown on the watch
   adb connect <watch-ip>:<connection-port> # a different port, shown on the Wireless debugging screen
   adb -s <watch-ip>:<connection-port> install -r wear/build/outputs/apk/debug/wear-debug.apk
   ```
   Reconnect after restarting wireless debugging or changing networks.
4. Open GlucoRAG on the watch once and accept the research notice.
5. Long-press the watch face → **Customise** → choose a complication slot → **GlucoRAG**: "Glucose
   now" (value, arrow and age) and "Next hour" (e.g. `Low` / `15m`). Faces with round slots take
   the short forms; large or edge slots take the sentence. Swipe to the tiles to add the GlucoRAG
   tile.

## What you see

| Situation | Watch / phone says |
|---|---|
| Low or high predicted | "Low predicted in 25 min" (the countdown keeps running on the watch face) |
| Already past 70 or 180 | "Low now" / "High now" |
| Band in range | "In range for the next hour" |
| Fewer than 2 hours of readings | "Collecting readings" |
| Server unreachable | "Forecast needs your GlucoRAG server" (current value still shown) |
| No reading for 15 min | "No recent reading", value greyed |
| Signed out on the server | Watch: "Open GlucoRAG on your phone"; phone: "Sign in again to see your forecast" |

## Testing without a phone–watch pair

Pairing emulators needs a Google Play phone image, a Google sign-in, the Pixel Watch app and
Android Studio's pairing assistant. Debug builds of the watch app accept a snapshot over adb
instead, through the same code path as the phone's:

```sh
adb -s <watch> shell am broadcast -a org.glucorag.wear.DEBUG_SNAPSHOT -p org.glucorag.app \
  --es json "$(cat scripts/snapshots/low-soon.json)"
```

`scripts/snapshots/` holds one snapshot per state (times are absolute; shift them to now). Send
CGM readings to the phone the same way the CGM apps do:

```sh
adb shell am broadcast -n org.glucorag.app/.source.GlucoseReceiver -a glucodata.Minute \
  --ei glucodata.Minute.mgdl 142 --el glucodata.Minute.Time $(($(date +%s)*1000)) --ef glucodata.Minute.Rate 0.4
adb shell am broadcast -n org.glucorag.app/.source.GlucoseReceiver -a com.eveningoutpost.dexdrip.BgEstimate \
  --ed com.eveningoutpost.dexdrip.Extras.BgEstimate 142.0 --el com.eveningoutpost.dexdrip.Extras.Time $(($(date +%s)*1000)) \
  --ed com.eveningoutpost.dexdrip.Extras.BgSlope 6.7e-6
```

`screenshots/` holds the emulator run: the phone (Android 15, light and dark) and the watch
(Wear OS 6 at 450 px and 396 px, the 46 mm and 42 mm screens) in every state.

## Known limits

- **Not verified on real hardware.** The phone→watch Data Layer link and notification mirroring
  were not tested on a paired phone and watch; Samsung's own watch faces were not tested (Google's
  Wear OS 6 faces were).
- **Phone and watch data may pass through Google's servers:** when Bluetooth is unavailable, the
  Wear OS Data Layer routes the snapshot through Google Cloud (end-to-end encrypted).
- **Any app on the phone can send a fake reading** to GlucoRAG's receiver: Android doesn't tell the
  receiver who sent a broadcast. Values outside 20–600 mg/dL or in the future are dropped.
- **The forecast needs your server.** Prediction runs only on the server; nothing is predicted on
  the phone.
- The development signing key is in the repository: build release APKs with your own key.
