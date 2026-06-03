#!/bin/sh
set -eu

cat > /usr/share/nginx/html/assets/meta-pixel.js <<EOF
(function () {
  var pixelId = "${META_PIXEL_ID:-}";
  var enabled = "${META_PIXEL_ENABLED:-true}";

  if (!pixelId || enabled === "false" || enabled === "0") {
    window.__META_PIXEL_ENABLED__ = false;
    return;
  }

  window.__META_PIXEL_ENABLED__ = true;

  !function(f,b,e,v,n,t,s)
  {if(f.fbq)return;n=f.fbq=function(){n.callMethod?
  n.callMethod.apply(n,arguments):n.queue.push(arguments)};
  if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
  n.queue=[];t=b.createElement(e);t.async=!0;
  t.src=v;s=b.getElementsByTagName(e)[0];
  s.parentNode.insertBefore(t,s)}(window, document,'script',
  'https://connect.facebook.net/en_US/fbevents.js');

  fbq('init', pixelId);
  fbq('track', 'PageView');
})();
EOF
