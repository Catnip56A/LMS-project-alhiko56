// Pop-up gallery items when they enter view; hide when they leave
(function(){
  function initGalleryPopups(){
    const items = document.querySelectorAll('#about .gallery-section .gallery-item');
    if (!items || items.length === 0) return;

    const opts = { root: null, rootMargin: '0px 0px -6% 0px', threshold: Array.from({length: 21}, (_,i)=>i/20) };

    function applyVisual(el, scale, opacity, translateY){
      window.requestAnimationFrame(() => {
        el.style.transform = `translateY(${translateY}px) scale(${scale})`;
        el.style.opacity = String(opacity);
      });
    }

    const io = new IntersectionObserver((entries) => {
      const vh = window.innerHeight || document.documentElement.clientHeight;
      const vCenter = vh / 2;

      entries.forEach(entry => {
        const el = entry.target;
        const rect = el.getBoundingClientRect();
        const elemCenter = rect.top + rect.height / 2;
        const distance = Math.abs(elemCenter - vCenter);
        const maxDist = (vh / 2) + (rect.height / 2);
        const t = Math.min(1, distance / maxDist);

        const scaleMin = 0.86;
        const scaleMax = 1.03;
        const opacityMin = 0.6;
        const opacityMax = 1.0;

        const scale = scaleMin + (1 - t) * (scaleMax - scaleMin);
        const opacity = opacityMin + (1 - t) * (opacityMax - opacityMin);
        const translateY = 18 * t;

        el.classList.add('will-animate');
        applyVisual(el, scale.toFixed(3), opacity.toFixed(2), Math.round(translateY));
      });
    }, opts);

    items.forEach(i => io.observe(i));

    let resizeTimer = null;
    window.addEventListener('resize', () => {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        items.forEach(i => io.unobserve(i));
        items.forEach(i => io.observe(i));
      }, 150);
    });
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(initGalleryPopups, 10);
  } else {
    document.addEventListener('DOMContentLoaded', initGalleryPopups);
  }

  // Enable horizontal drag/scroll and wheel-to-scroll for About page feature and gallery lists
  function enableHorizontalScroll(selector){
    const el = document.querySelector(selector);
    if (!el) return;
    let isDown = false;
    let startX, scrollLeft;

    el.style.cursor = 'grab';

    el.addEventListener('pointerdown', (e) => {
      isDown = true;
      el.setPointerCapture && el.setPointerCapture(e.pointerId);
      startX = e.clientX;
      scrollLeft = el.scrollLeft;
      el.style.cursor = 'grabbing';
    });

    el.addEventListener('pointermove', (e) => {
      if (!isDown) return;
      const x = e.clientX;
      const walk = (startX - x);
      el.scrollLeft = scrollLeft + walk;
    });

    el.addEventListener('pointerup', (e) => {
      isDown = false;
      el.releasePointerCapture && el.releasePointerCapture(e.pointerId);
      el.style.cursor = 'grab';
    });

    el.addEventListener('pointerleave', (e) => {
      isDown = false;
      el.style.cursor = 'grab';
    });

    el.addEventListener('wheel', (ev) => {
      if (Math.abs(ev.deltaY) > Math.abs(ev.deltaX)) {
        ev.preventDefault();
        el.scrollLeft += ev.deltaY;
      }
    }, { passive: false });
  }

  function initAboutHorizontal(){
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
      setTimeout(() => {
        enableHorizontalScroll('#about .gallery-grid');
      }, 30);
    } else {
      document.addEventListener('DOMContentLoaded', () => {
        enableHorizontalScroll('#about .gallery-grid');
      });
    }
  }

  initAboutHorizontal();

  // Arrow buttons removed per request (static buttons now in index.html template for both galleries)

  function initFeatureSelection(){
    const list = document.querySelector('#about .features-list');
    if (!list) return;
    const items = Array.from(list.querySelectorAll('.feature-card'));
    if (items.length === 0) return;
    items.forEach(item => {
      item.addEventListener('click', () => { items.forEach(i => i.classList.toggle('active', i === item)); });
      item.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); item.click(); } });
    });
  }
  if (document.readyState === 'complete' || document.readyState === 'interactive') initFeatureSelection(); else document.addEventListener('DOMContentLoaded', initFeatureSelection);
})();

/* ----- Orbit placement and hover-description overlay ----- */
(function(){
  function initFeatureOrbit(){
    const wrap = document.querySelector('#about .features');
    const orbitContainer = document.querySelector('#about .features-list');
    const originalCards = Array.from(document.querySelectorAll('#about .features-list .feature-card'));
    const core = document.querySelector('#about .feature-core');
    const coreTitle = core ? core.querySelector('.core-title') : null;
    const coreSub = core ? core.querySelector('.core-sub') : null;
    const coreDesc = document.querySelector('#about .core-desc');
    if (!wrap || !orbitContainer || originalCards.length === 0 || !core) return;

    // populate core title/sub from section header (store texts for typewriter)
    const featuresSection = wrap.closest('.features-section') || document.querySelector('#about .features-section');
    let coreTitleText = '';
    let coreSubText = '';
    if (featuresSection && coreTitle) {
      const secTitleEl = featuresSection.querySelector('.section-title');
      const secP = featuresSection.querySelector('p');
      coreTitleText = secTitleEl ? secTitleEl.textContent.trim() : '';
      coreSubText = secP ? secP.textContent.trim() : '';
      // clear visual content; we'll render them via typewriter
      coreTitle.textContent = '';
      if (coreSub) coreSub.textContent = '';
    }

    // Hide original card elements (they remain as data sources)
    originalCards.forEach(c => { c.style.display = 'none'; });

    // Build items from data-* attributes
    const items = originalCards.map(c => ({ title: c.dataset.title || '', sub: c.dataset.sub || '', desc: c.dataset.desc || '', fullTitle: c.dataset.title || '' }));

    // Create an SVG overlay with circular paths + textPaths
    function createSVGOverlay(){
      try {
        // remove previous svg if any
        const existing = orbitContainer.querySelector('svg');
        if (existing) existing.remove();

        const wrapRect = wrap.getBoundingClientRect();
        const coreRect = core.getBoundingClientRect();
        const width = Math.max(320, Math.round(wrapRect.width));
        const height = Math.max(320, Math.round(wrapRect.height));
        const cx = (coreRect.left - wrapRect.left) + coreRect.width / 2;
        const cy = (coreRect.top - wrapRect.top) + coreRect.height / 2;
        const r = Math.max(coreRect.width, coreRect.height) / 2 + Math.min(140, Math.min(wrapRect.width, wrapRect.height) / 4);

        const SVG_NS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(SVG_NS, 'svg');
        svg.setAttribute('width', width);
        svg.setAttribute('height', height);
        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
        svg.classList.add('orbit-svg');
        svg.style.position = 'absolute';
        svg.style.left = '0';
        svg.style.top = '0';
        svg.style.width = '100%';
        svg.style.height = '100%';
        svg.style.pointerEvents = 'none';

        const defs = document.createElementNS(SVG_NS, 'defs');
        svg.appendChild(defs);

        const group = document.createElementNS(SVG_NS, 'g');
        group.setAttribute('class','orbit-group');
        svg.appendChild(group);

        const nodes = [];
        // Create <path> + <text><textPath> elements so titles follow the circular path
        items.forEach((it, idx) => {
          const path = document.createElementNS(SVG_NS, 'path');
          const pathId = `orbitPath-${Date.now()}-${idx}`;
          const d = `M ${cx - r} ${cy} a ${r} ${r} 0 1 0 ${2*r} 0 a ${r} ${r} 0 1 0 ${-2*r} 0`;
          path.setAttribute('d', d);
          path.setAttribute('id', pathId);
          defs.appendChild(path);

          const text = document.createElementNS(SVG_NS, 'text');
          text.setAttribute('class', 'orbit-text-svg');
          text.setAttribute('tabindex', '0');
          text.setAttribute('text-anchor', 'middle');
          const textPath = document.createElementNS(SVG_NS, 'textPath');
          try { textPath.setAttribute('href', `#${pathId}`); } catch(e){ textPath.setAttributeNS('http://www.w3.org/1999/xlink', 'xlink:href', `#${pathId}`); }
          // center each title inside its slot
          const startOffsetPercent = (((idx + 0.5) / items.length) * 100).toFixed(4) + '%';
          textPath.setAttribute('startOffset', startOffsetPercent);
          textPath.textContent = it.title || '';
          text.appendChild(textPath);
          group.appendChild(text);

          // Store the index directly on the text element for reliable retrieval
          text.dataset.itemIndex = idx;
          console.log(`Created item ${idx}: title="${it.title}", dataset.itemIndex=${text.dataset.itemIndex}`);

          // pointer events on the text element — press to select/rotate to bottom
          text.style.pointerEvents = 'auto';
          text.addEventListener('pointerdown', (e)=>{ e.preventDefault(); const i = parseInt(e.currentTarget.dataset.itemIndex, 10); console.log(`Clicked item with idx=${i}, title="${e.currentTarget.textContent}"`); startRotateToIndex(i); });
          text.addEventListener('keydown', (ev)=>{ if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); const i = parseInt(ev.currentTarget.dataset.itemIndex, 10); startRotateToIndex(i); } });

          // adaptive font-size: shrink text until it fits a safe portion of the path
          try {
            const pathLen = path.getTotalLength();
            const maxAllowed = pathLen * 0.6;
            let fontPx = 16;
            text.style.fontSize = fontPx + 'px';
            let measured = text.getComputedTextLength ? text.getComputedTextLength() : 0;
            while (measured > maxAllowed && fontPx > 10) {
              fontPx -= 1;
              text.style.fontSize = fontPx + 'px';
              measured = text.getComputedTextLength ? text.getComputedTextLength() : measured;
            }
            if (measured > maxAllowed) {
              let full = items[idx].fullTitle || (it.title||'');
              let truncated = full;
              while (truncated.length > 3) {
                truncated = truncated.slice(0, -1);
                textPath.textContent = truncated + '…';
                measured = text.getComputedTextLength ? text.getComputedTextLength() : measured;
                if (measured <= maxAllowed) break;
              }
            } else {
              textPath.textContent = it.title || '';
            }
          } catch (e) {
            // ignore measurement errors in older browsers
          }

          nodes.push({ text, path, textPath, idx });
        });

        orbitContainer.appendChild(svg);
        return { svg, group, nodes, cx, cy, r };
      } catch (err) {
        // ensure we never throw so UI remains visible; return a safe fallback
        try { console.error('createSVGOverlay error', err); } catch(e){}
        // remove existing svg if in inconsistent state
        try { const existing = orbitContainer.querySelector('svg'); if (existing) existing.remove(); } catch(e){}
        const fallback = document.createElement('div');
        fallback.className = 'orbit-fallback';
        orbitContainer.appendChild(fallback);
        return { svg: null, group: null, nodes: [], cx: 0, cy: 0, r: 0 };
      }
    }

    // typewriter helper (only invoked when active item changes)
    let typingTimer = null;
    function typewriter(el, text){ if (!el) return; el.classList.add('typewriter'); el.textContent = ''; let i=0; if (typingTimer) clearInterval(typingTimer); typingTimer = setInterval(()=>{ if (i<text.length) { el.textContent += text.charAt(i); i++; } else { clearInterval(typingTimer); typingTimer=null; el.classList.remove('typewriter'); } }, 20); }

    // helper to show core title and subtitle using typewriter sequentially
    function showCoreTitleSub(title, sub){
      if (!coreTitle) return;
      if (typingTimer) { clearInterval(typingTimer); typingTimer = null; }
      coreTitle.textContent = '';
      coreTitle.classList.remove('typewriter');
      if (coreSub) { coreSub.textContent = ''; coreSub.classList.remove('typewriter'); }
      typewriter(coreTitle, title || '');
      // schedule subtitle after title finishes (approx 20ms per char)
      const delay = (title ? title.length * 20 : 0) + 160;
      setTimeout(()=>{ if (coreSub) typewriter(coreSub, sub || ''); }, delay);
    }

    // Rotation & selection state
    const speed = 0.0004; // radians per ms — auto-rotate speed
    let angleOffset = 0;
    let lastTs = null;
    // Selection/rotation-to-target
    let selectedIndex = null; // index that has been brought to bottom and is active
    let rotatingToIndex = null; // index currently being animated to bottom
    let rotationTargetOffset = null; // target angleOffset for rotationTo
    // slower rotate-to speed for a smoother downward transition
    const rotationToSpeed = 0.0025; // radians per ms when rotating to a selected item
    const rotationTolerance = 0.02; // radians — threshold to consider 'at bottom'
    let pauseUntil = null; // timestamp (ms) until which auto-rotation is paused after selection
    // Rotation-once control (run a single full revolution then stop)
    let rotateOnlyOnce = false; // continuous rotation when false
    let rotateRemaining = rotateOnlyOnce ? (Math.PI * 2) : Infinity;
    let rotationCompleted = false;

    // remove any leftover upright overlays from prior experiments
    try {
      document.querySelectorAll('.orbit-uncurved-upright, .orbit-uncurved-overlay').forEach(n=>n.remove());
    } catch(e){}

    let overlay = createSVGOverlay();
    // ensure curved svg text nodes are visible
    try { overlay.nodes.forEach(n => { if (n && n.text) n.text.style.visibility = ''; }); } catch(e){}
    // show core title/sub on load using typewriter
    try { showCoreTitleSub(coreTitleText, coreSubText); } catch (e) { /* ignore */ }

    let lastActiveDesc = null;
    function shortestAngle(a){
      // normalize to [-PI, PI]
      a = ((a + Math.PI) % (Math.PI*2)) - Math.PI;
      return a;
    }

    function applySelectedStyle(idx){
      if (idx == null) return;
      try {
        const n = overlay.nodes[idx];
        if (!n || !n.text) return;
        // bump font-size and weight for emphasis
        const cur = parseFloat((n.text.style.fontSize||'16').replace('px','')) || 16;
        n._prevFontSize = n.text.style.fontSize;
        n._prevFontWeight = n.text.style.fontWeight;
        n.text.style.fontWeight = '700';
        n.text.style.fontSize = Math.round(cur * 1.35) + 'px';
      } catch(e){}
    }

    function removeSelectedStyle(idx){
      try {
        if (idx == null) return;
        const n = overlay.nodes[idx];
        if (!n || !n.text) return;
        if (n._prevFontSize !== undefined) n.text.style.fontSize = n._prevFontSize; else n.text.style.fontSize = '';
        if (n._prevFontWeight !== undefined) n.text.style.fontWeight = n._prevFontWeight; else n.text.style.fontWeight = '';
      } catch(e){}
    }

    function startRotateToIndex(idx){
      if (!overlay || !overlay.nodes || overlay.nodes.length === 0) return;
      const count = overlay.nodes.length;
      const base = ((idx) / count) * Math.PI * 2;
      const targetAngle = (3 * Math.PI / 2);;
      // We want: base + angleOffset = PI/2 (bottom position)
      // Therefore: angleOffset = PI/2 - base
      let desired = targetAngle - base;
      // choose closest equivalent target to current angleOffset
      const k = Math.round((desired) / (Math.PI*2));
      const target = desired + k * Math.PI*2;
      
      rotationTargetOffset = target;
      rotatingToIndex = idx;
      // clear any prior selected styling while rotating
      if (selectedIndex !== null && selectedIndex !== rotatingToIndex) {
        removeSelectedStyle(selectedIndex);
        selectedIndex = null;
      }
      // cancel any active pause — we'll set a fresh pause when rotation completes
      pauseUntil = null;
    }

    function animate(ts){
      if (!lastTs) lastTs = ts;
      const dt = ts - lastTs;
      lastTs = ts;
      if (rotatingToIndex !== null) {
        // animate angleOffset towards rotationTargetOffset at a faster tempo
        const delta = shortestAngle(rotationTargetOffset - angleOffset);
        const maxStep = rotationToSpeed * dt;
        if (Math.abs(delta) <= Math.max(rotationTolerance, maxStep)) {
          angleOffset = rotationTargetOffset;
          // reached bottom for the rotated-to item
          selectedIndex = rotatingToIndex;
          applySelectedStyle(selectedIndex);
          rotatingToIndex = null;
          rotationTargetOffset = null;
          // pause auto-rotation for 15s (or until next item selected)
          pauseUntil = ts + 15000;
        } else {
          angleOffset += Math.sign(delta) * maxStep;
        }
      } else {
        // if currently in pause period, check expiry and resume auto-rotation after
        if (pauseUntil !== null && ts >= pauseUntil) {
          // pause expired — remove selected styling and resume
          if (selectedIndex !== null) { removeSelectedStyle(selectedIndex); selectedIndex = null; }
          pauseUntil = null;
        }

        if (rotateOnlyOnce && !rotationCompleted) {
          const delta = speed * dt;
          angleOffset += delta;
          rotateRemaining -= delta;
          if (rotateRemaining <= 0) {
            rotationCompleted = true;
            rotateRemaining = 0;
          }
        } else if (!rotateOnlyOnce) {
          // respect active pause
          if (pauseUntil !== null && ts < pauseUntil) {
            // do nothing — paused
          } else {
            angleOffset += speed * dt;
          }
        }
      }

      const count = overlay.nodes.length;
      let topIdx = 0;
      let topY = Infinity;
      for (let i=0;i<count;i++){
        const base = (i / count) * Math.PI * 2;
        const a = base + angleOffset;
        const y = overlay.cy + Math.sin(a) * overlay.r;
        if (y < topY) { topY = y; topIdx = i; }
      }

      // while rotating to a choice, hide the section title/sub
      if (rotatingToIndex !== null) {
        try { if (coreTitle) coreTitle.style.visibility = 'hidden'; } catch(e){}
        try { if (coreSub) coreSub.style.visibility = 'hidden'; } catch(e){}
        if (coreDesc) { coreDesc.style.display = 'none'; coreDesc.innerHTML = ''; }
        lastActiveDesc = null;
      }

      // show the selected item's title/sub in the core (instead of section title/sub)
      else if (selectedIndex !== null && items[selectedIndex]) {
        if (lastActiveDesc !== selectedIndex) {
          // show title/sub of the selected item via typewriter
          showCoreTitleSub(items[selectedIndex].title || '', items[selectedIndex].sub || '');
          lastActiveDesc = selectedIndex;
        }
        // ensure coreDesc is hidden
        if (coreDesc) { coreDesc.style.display = 'none'; coreDesc.innerHTML = ''; }
      } else {
        // no selection: ensure core shows section title/sub (typewriter) if we transitioned
        if (lastActiveDesc !== null) {
          showCoreTitleSub(coreTitleText, coreSubText);
        }
        lastActiveDesc = null;
        try { if (coreTitle) coreTitle.style.visibility = ''; } catch(e){}
        try { if (coreSub) coreSub.style.visibility = ''; } catch(e){}
      }

      // rotate the svg group so textPaths orbit the core
      const deg = (angleOffset * 180 / Math.PI) % 360;
      if (overlay.svg){
        overlay.svg.style.transformOrigin = `${overlay.cx}px ${overlay.cy}px`;
        overlay.svg.style.transform = `rotate(${deg}deg)`;
      }

        // flipping disabled

      requestAnimationFrame(animate);
    }

    window.addEventListener('resize', ()=>{ lastTs = null; overlay = createSVGOverlay(); });
    requestAnimationFrame(animate);

    // flipping feature removed; no overlay flip behavior present
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') initFeatureOrbit(); else document.addEventListener('DOMContentLoaded', initFeatureOrbit);
})();
