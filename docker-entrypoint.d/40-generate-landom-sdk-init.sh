#!/bin/sh
set -eu

cat > /usr/share/nginx/html/assets/landom-sdk-init.js <<EOF
(function () {
  var endpoint = "${LANDOM_SDK_ENDPOINT:-/api/v1/events}";
  var configs = {
    "/landom": { service: "landom", apiKey: "${LANDOM_SDK_API_KEY:-}" },
    "/attune": { service: "attune", apiKey: "${ATTUNE_SDK_API_KEY:-}" },
    "/sian": { service: "sian", apiKey: "${SIAN_SDK_API_KEY:-}" },
    "/soom": { service: "soom", apiKey: "${SOOM_SDK_API_KEY:-}" },
    "/moyo": { service: "moyo", apiKey: "${MOYO_SDK_API_KEY:-}" }
  };

  var pathname = window.location.pathname.replace(/\\/+$/, "") || "/landom";
  var firstSegment = "/" + pathname.split("/").filter(Boolean)[0];
  var config = configs[pathname] || configs[firstSegment];

  if (!config || !config.apiKey) {
    console.warn("[LandOm SDK] Missing SDK apiKey for", pathname);
    return;
  }

  if (!window.LandOm || typeof window.LandOm.init !== "function") {
    console.warn("[LandOm SDK] CDN script was not loaded.");
    return;
  }

  window.LandOm.init({
    apiKey: config.apiKey,
    endpoint: endpoint,
    enableReplay: true,
    replayMaskAllInputs: true,
    replayBlockSelector: ".no-record",
    replayMaskTextClass: "rr-mask",
    debug: false,
    beforeSend: function (event) {
      event.payload = event.payload || {};
      event.payload.service = config.service;
      return event;
    }
  });
})();
EOF
