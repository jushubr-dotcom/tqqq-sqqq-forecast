// Default user settings, shared by the content script and the popup.
var DUALSUBS_DEFAULTS = {
  enabled: true,
  myLang: (navigator.language || 'en').split('-')[0],
  origLang: 'auto',
  fontSize: 26,
  bottom: 10, // % of video height
  origOnTop: true,
  hideNative: true,
  offset: 0, // seconds; positive shows subtitles later
};
