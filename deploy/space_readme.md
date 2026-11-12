---
title: Bidding Helper AI
emoji: 🏗️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Bidding Helper AI

Upload an EPADS tender PDF and the app will:

- read the BOQ and check it against the totals printed in the tender,
- let you edit rates in plain words (with a preview first) and download the Excel file,
- answer questions about requirements, forms, dates and security, with page numbers,
- translate item descriptions into Urdu.

**Bring your own free API key** (Gemini from aistudio.google.com/apikey, or Groq from console.groq.com/keys) and paste it in the sidebar.

**Privacy:** your PDF is read on this server and kept in memory only for your session; it is never saved.
Your keys stay in your browser session. The passages of the tender needed for a question are sent to Google
(Gemini) or Groq using your own key.

Always check results against the tender before bidding.
