# SmartSeat visual assets

The design follows the warm dark surfaces, status colors and service hierarchy of the user-supplied DineAssist reference. It uses original SmartSeat layouts with actual camera and restaurant data.

24 decorative backgrounds are stored in `web/public/assets/backgrounds/scene-00.webp` through `scene-23.webp`. They are CSS backgrounds only, independent of camera inference. `credits.json` records each source and license. Photographs downloaded from Unsplash use its standard license; they are not a photo redistribution service. They have no runtime dependency on Unsplash or a paid API.

`scene-00.webp` was generated using the built-in Image Gen tool, then optimized locally for delivery. Prompt: wide cinematic photograph of an empty boutique restaurant at dusk, brass table lamp, candle and glassware on dark marble in the right third, olive branches, velvet dark olive seating, warm pendant bokeh, deep espresso left negative space, honey/ivory highlights; no people, lettering, branding, UI or CCTV imagery. The reference concept is retained in the Codex generated-images folder; no generated dashboard screenshot is shipped as application UI.

Local fonts are in `web/public/assets/fonts/`: DM Sans for controls and body, Instrument Serif for selected display treatments, and the system Georgia serif for headings. Google Fonts source files use the included SIL Open Font License notices. Text and controls are real HTML, not rasterized labels.

Background photographs crossfade every 20 seconds and can be advanced manually. The pause control persists per browser. Reduced-motion preferences disable animation; background rotation stops in hidden tabs. Only the next ambient scene is prefetched. The full set is about 8 MB on disk; initial rendering does not fetch all 24 photographs.
