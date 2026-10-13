# Dual Subtitles

A Chrome extension (Manifest V3, also works in Edge, Brave and Opera) that shows subtitles in **two languages at once**: the language the video was made in, with your own language underneath.

Works on **YouTube**, **Netflix** and **Prime Video** (primevideo.com and Prime Video on amazon.com, .co.uk, .de, .co.jp, .ca, .fr, .it, .es, .in, .com.au, .com.br, .com.mx, .nl).

It's a paid extension with a **free 1-month trial**. Payments go through [ExtensionPay](https://extensionpay.com), which runs on Stripe.

![Overlay](docs/overlay.png) ![Popup](docs/popup.png)

## How it works

| Site | Where the subtitles come from | Your language |
| --- | --- | --- |
| YouTube | The player's caption tracks. The extension reuses the signed `timedtext` request the player makes, so captions are turned on briefly in the background. The original language comes from the auto-generated track, which is always in the spoken language. | A human-made track in your language if the video has one, otherwise YouTube's own auto-translate (`tlang`). |
| Netflix | The title manifest, captured in the page. The extension also asks Netflix to include WebVTT files. The original language is the audio track Netflix marks as native. | Netflix's track in your language. If there isn't one, the original track is machine-translated. |
| Prime Video | The `GetPlaybackResources` response, which lists a TTML file per language. | Prime's track in your language. If there isn't one, the original track is machine-translated. |

Both lines are drawn in one overlay that follows the video, including in fullscreen. By default the site's own subtitles are hidden so you don't see three lines. In the popup you can set your language, override the original language, change text size and position, flip which line is on top, and shift the timing.

### Code layout

```
src/
  manifest.json
  config.js            ExtensionPay ID, trial length, optional translation key
  background.js        License checks, subtitle downloads, machine translation
  page-hook.js         Runs in the page (MAIN world): watches the players' own requests
  content.js           Paywall, loads both tracks, renders the overlay
  adapters/            One file per site: youtube.js, netflix.js, prime.js
  lib/subs.js          Parsers (YouTube json3, WebVTT, TTML/DFXP), cue lookup, track picking
  popup.html/.js/.css  Settings and account
  welcome.html         Opens on install, with a "Start my free month" button
  vendor/ExtPay.js     ExtensionPay client 3.1.2 (LGPL-3.0, unmodified)
test/                  Unit tests: npm test
```

To support another site, add a file to `src/adapters/` with `match`, `init`, `currentKey` and `resolve` (copy `netflix.js` as a starting point), then add its URL patterns to `manifest.json`.

## Try it locally

1. Open `chrome://extensions` and turn on **Developer mode**.
2. Click **Load unpacked** and pick the `src/` folder.
3. Open a YouTube video that has subtitles.

Until payments are set up (next section), the trial button can't work, because `config.js` contains a placeholder ExtensionPay ID.

## Set up payments (free trial, then a subscription)

1. Sign up at [extensionpay.com](https://extensionpay.com), connect your Stripe account and register an extension. Copy its ID into `extensionPayId` in `src/config.js`.
2. In the ExtensionPay dashboard, create the plan you want, for example **$4.99/month** or **$39/year**. The price is set there, not in the code.
3. The trial length is `trialDays` in `src/config.js` (30). When a user clicks **Start free trial**, ExtensionPay asks for their email and records the trial start date. The extension unlocks while `now < trialStartedAt + 30 days`. After that it shows a **Subscribe** prompt on the video page and in the popup.
4. The trial is tied to the email address, so uninstalling and reinstalling doesn't give anyone a second month. Users who pay can sign in on other browsers with **Already paid? Log in**.
5. If ExtensionPay can't be reached, the last known status is trusted for 3 days so a paying user isn't locked out while offline.

### Machine translation

On YouTube, translation is free because it uses YouTube's own auto-translate. On Netflix and Prime Video it's only needed when the title has no subtitle track in the viewer's language.

- **Before you sell the extension**, put a [Google Cloud Translation](https://cloud.google.com/translate) API key in `googleTranslateApiKey` in `src/config.js`. It costs about $20 per million characters, which is roughly 25–40 feature-length films.
- If you leave it empty, the extension uses Google's keyless `translate_a` endpoint. That's fine for development, but it isn't an official API and can be rate-limited.

## Publish

1. `npm run zip` creates `dual-subtitles.zip` from `src/`.
2. Upload it in the [Chrome Web Store developer dashboard](https://chrome.google.com/webstore/devconsole) (one-time $5 fee). Use the screenshots in `docs/`.
3. In the listing, say that the extension is paid with a 1-month free trial. Explain each permission: site access to read subtitles on YouTube, Netflix and Prime Video; the subtitle CDNs (`nflxvideo.net`, `cloudfront.net`, `media-amazon.com`); Google translation; and `extensionpay.com` for payments.
4. Edge Add-ons accepts the same zip.

## Limitations

- Netflix and Prime Video change their players often. If subtitles stop appearing on one site, that site's adapter in `src/adapters/` is the place to fix it.
- Netflix: reload the tab if you open a title in a tab that was already open before the extension was installed.
- Prime Video sometimes starts the video timeline a few seconds off. Fix it with **Timing offset** in the popup.
- The paywall runs in the browser, as it does for every extension that uses ExtensionPay. A determined user could bypass it.
- Not tested yet against the live Netflix and Prime Video sites. The end-to-end check ran the real extension in Chromium against simulated YouTube, Netflix and Prime pages and API responses (see below).

## Tests

```
npm test
```

Unit tests cover the subtitle parsers (YouTube json3, WebVTT, TTML/DFXP with ticks, clock times, line breaks and split regions), cue lookup, and choosing the original and viewer-language tracks.

During development the extension was also loaded unpacked in Chromium against simulated YouTube, Netflix and Prime Video pages. With mocked ExtensionPay responses, that check confirmed:

- the paywall appears with no account and after the trial expires;
- both subtitle lines appear and the native captions are hidden during the trial;
- machine translation runs when the title has no track in the viewer's language;
- the popup shows the trial days left.
