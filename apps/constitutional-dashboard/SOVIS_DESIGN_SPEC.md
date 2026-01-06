# 📺 Sovis (Google Nest Hub) Design Specifications

## Skärmformat & Tekniska Specifikationer

### Display
- **Resolution:** 1024 x 600 pixels
- **Aspect Ratio:** 16:9 (widescreen)
- **Screen Size:** 7" touchscreen
- **Orientation:** Landscape (horisontell)
- **Touch:** Full touch support (multi-touch)

### Viktiga Designbegränsningar

#### 1. **INGEN SCROLL**
- Skärmen är fixerad till 1024x600
- Allt måste passa inom viewport
- `overflow: hidden` på alla nivåer
- Använd `position: fixed` för html/body
- Max-height: 600px, Max-width: 1024px

#### 2. **Touch-Friendly Design**
- **Minimum touch target:** 44x44px (rekommenderat 48x48px)
- **Button spacing:** Minst 8-10px mellan knappar
- **Text size:** Minst 12px för läsbarhet
- Använd `touch-action: manipulation` för snabbare respons

#### 3. **Layout System**
- **Current layout:** 3-kolumns grid
  - Vänster (25%): Vitals (VRAM gauge, CPU/Context circles)
  - Mitten (40%): Monitor (Status orb, Log stream, TPS)
  - Höger (35%): Actions (3 stora knappar)
- **Gap:** 10px mellan kolumner
- **Padding:** 10px på alla zoner

#### 4. **Färgpalett (Nuvarande - Original Deep Void)**
```css
--bg: #0a0a0a                    /* Svart bakgrund */
--panel: rgba(8, 10, 12, 0.85)   /* Mörka paneler */
--text: rgba(240, 255, 255, 0.92) /* Vit text */
--muted: rgba(240, 255, 255, 0.55) /* Dimmad text */
--cyan: #00f3ff                   /* Cyan accent */
--ok: #33ff9a                     /* Grön (OK status) */
--warn: #ffcc00                    /* Gul (Varning) */
--danger: #ff365c                  /* Röd (Kritisk) */
```

#### 5. **Bakgrund**
- Gradient med cyan/purple glow:
```css
background: radial-gradient(1200px 600px at 20% 10%, rgba(0, 243, 255, 0.08), transparent 45%),
            radial-gradient(900px 500px at 80% 30%, rgba(255, 54, 92, 0.06), transparent 50%),
            linear-gradient(180deg, #070707 0%, #0a0a0a 100%);
```

## Komponenter & Dimensioner

### VRAM Gauge
- **Height:** 140px (vertikal stapel)
- **Width:** 100% av kolumn
- **Färglogik:**
  - Grön: < 10GB
  - Gul: > 10GB
  - Röd: > 11.5GB

### Status Pulse Orb
- **Size:** 60x60px
- **States:**
  - 🟢 ONLINE (grön)
  - 🔵 SEARCHING (cyan)
  - 🟣 GENERATING (lila)
  - 🔴 OFFLINE (röd)
- **Animation:** Pulse (scale 1.0 → 1.1)

### Load Circles (CPU/Context)
- **Size:** 80% width, max 100px
- **Stroke width:** 8px
- **Circumference:** 283px (2 * π * 45)

### Black Box (Log Stream)
- **Height:** Flex (tar resten av Monitor-zonen)
- **Font:** JetBrains Mono, 10px
- **Lines:** Visar 3 senaste raderna
- **Background:** rgba(8, 10, 12, 0.62)

### Action Buttons
- **Height:** Flex (delar utrymme jämnt)
- **Min-height:** Ingen (använder flex: 1)
- **Padding:** 10px
- **Border:** 1px solid rgba(0, 243, 255, 0.22)
- **Hover:** Cyan glow + translateY(-2px)

### Performance Metric (TPS)
- **Font size:** 24px (stor)
- **Color:** Cyan (#00f3ff)

## Typografi

### Font Sizes
- **Titles:** 10-12px (uppercase, letter-spacing: 0.1em)
- **Values:** 14-24px (beroende på vikt)
- **Labels:** 10-11px (uppercase, muted color)
- **Log text:** 10px (monospace)

### Font Family
- **UI:** ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto
- **Code/Log:** "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco

## Interaktioner

### Touch Events
- Använd `pointerup` + `click` fallback
- `touch-action: manipulation` för snabbare respons
- Hover-states fungerar (touch + hold)

### Button States
- **Normal:** Border med cyan accent
- **Hover:** Cyan glow + shadow
- **Active:** translateY(0) (tryck-effekt)
- **Working:** Pulse animation
- **Success:** Grön border + background
- **Error:** Röd border + background

## Viewport & Meta Tags

```html
<meta name="viewport" content="width=1024, height=600, initial-scale=1, maximum-scale=1, user-scalable=no" />
<meta name="theme-color" content="#0a0a0a" />
```

## CSS Grid System

```css
.dashboard {
  display: grid;
  grid-template-columns: 25% 40% 35%;
  height: 100vh;
  width: 100vw;
  gap: 10px;
  padding: 10px;
  overflow: hidden;
}
```

## Viktiga CSS-regler

### Inga scrollbars
```css
html, body {
  overflow: hidden;
  position: fixed;
  max-height: 600px;
  max-width: 1024px;
}
```

### Flexbox för dynamisk höjd
```css
.zone-vitals, .zone-monitor, .zone-actions {
  display: flex;
  flex-direction: column;
  min-height: 0;  /* Viktigt för flex children */
  overflow: hidden;
}
```

### Glass Panel Effect
```css
background: rgba(8, 10, 12, 0.85);
border: 1px solid rgba(0, 243, 255, 0.22);
box-shadow: 0 0 0 1px rgba(0, 243, 255, 0.07) inset,
            0 18px 40px rgba(0, 0, 0, 0.35);
```

## Performance Considerations

- **Polling:** Dashboard pollar `/api/stats` var 1000ms (1 sekund)
- **Animations:** Använd `transform` och `opacity` (GPU-accelererat)
- **Backdrop-filter:** Kan vara tungt, testa performance
- **Transitions:** Max 0.5s för smooth animations

## Testing Checklist

- [ ] Allt syns utan scroll
- [ ] Touch targets är minst 44x44px
- [ ] Text är läsbar (minst 10px)
- [ ] Knappar fungerar med touch
- [ ] Layout fungerar på exakt 1024x600
- [ ] Inga element går utanför viewport
- [ ] Färger har tillräcklig kontrast
- [ ] Animations är smooth (60fps)

## Filer att Redigera

- **CSS:** `/static/deep-void.css`
- **HTML:** `/templates/index.html`
- **JavaScript:** `/static/dashboard.js`

## Cast Information

- **URL:** `http://192.168.86.32:5000`
- **Device:** Sovis (Google Nest Hub)
- **Auto-cast:** Systemd service (`constitutional-cast.service`)
- **Keepalive:** Recastar automatiskt var 30:e sekund

## Tips för Designers

1. **Testa alltid på exakt 1024x600** - använd browser dev tools
2. **Använd flexbox** för dynamisk layout istället för fixed heights
3. **Cyan är accent-färgen** - använd sparsamt för maximal impact
4. **Mörka paneler** ger djup - använd shadows för 3D-effekt
5. **Monospace för loggar** - lättare att läsa kod/system output
6. **Stora siffror** för viktiga metrics (TPS, VRAM)
7. **Status colors** - grön=gott, gul=varning, röd=kritisk
