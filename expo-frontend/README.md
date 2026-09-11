# Souveno Expo Agent — frontend

Static app (no build step): `index.html` (in-app dashboard: events, itinerary, approvals, finance, funds, leads,
stall picker, travel, settings, voice), `card.html` (public card / QR page), `dashboard/command_center_template.html`
(the phone command center, built by `expo-backend/scripts/build_dashboard.py` and published as a Claude artifact).

```
# point it at the API
echo "window.EXPO_API_BASE = 'https://<your-expo-backend>';" > config.js
python -m http.server 8080           # or any static host (Vercel, Netlify, GitHub Pages)
```

Leave `config.js` empty (same origin) when the backend serves this folder via `EXPO_FRONTEND_DIR`.
