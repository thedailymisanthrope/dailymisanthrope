// ============================================================
// THE DAILY MISANTHROPE — Client-side rendering
// ============================================================

(function () {
  'use strict';

  // --- Theme Toggle (click the clown) ---
  const toggle = document.querySelector('[data-theme-toggle]');
  const root = document.documentElement;
  let theme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  root.setAttribute('data-theme', theme);

  if (toggle) {
    toggle.addEventListener('click', () => {
      theme = theme === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', theme);
      toggle.setAttribute('aria-label', 'Switch to ' + (theme === 'dark' ? 'light' : 'dark') + ' mode');
    });
  }

  // --- Footer year ---
  document.getElementById('footer-year').textContent = new Date().getFullYear();

  // --- Load stories ---
  fetch('./data/stories.json')
    .then(r => r.json())
    .then(render)
    .catch(err => {
      console.error('Failed to load stories:', err);
      document.getElementById('folly-content').innerHTML =
        '<p style="color:var(--color-text-muted); font-style:italic;">Today\'s folly could not be retrieved. Perhaps that is itself the folly.</p>';
    });

  function render(data) {
    renderTreadwell(data);
    renderVideo(data);
    // Edition line
    document.getElementById('edition-line').textContent = data.edition || '';

    // Epigraph
    if (data.epigraph) {
      document.getElementById('epigraph-text').textContent = '"' + data.epigraph.text + '"';
      document.getElementById('epigraph-attr').textContent = '— ' + data.epigraph.attribution;
    }

    // Misanthrope Index
    if (data.misanthropeIndex) {
      const pct = (data.misanthropeIndex.value / 10) * 100;
      const bar = document.getElementById('index-bar');
      const val = document.getElementById('index-value');

      // Animate the bar
      requestAnimationFrame(() => {
        bar.style.width = pct + '%';
      });
      // Animate count-up
      animateValue(val, 0, data.misanthropeIndex.value, 800);
    }

    // Folly of the Day
    if (data.follyOfTheDay) {
      const f = data.follyOfTheDay;
      document.getElementById('folly-content').innerHTML = `
        <h2 class="folly-headline">${escapeHtml(f.headline)}</h2>
        <span class="folly-category">${escapeHtml(f.category)}</span>
        <p class="folly-summary">${escapeHtml(f.summary)}</p>
        <blockquote class="folly-commentary">${escapeHtml(f.commentary)}</blockquote>
        <p class="folly-source">Source: <a href="${escapeAttr(f.sourceUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(f.source)}</a></p>
      `;
    }

    // Wire stories
    const wireList = document.getElementById('wire-list');
    if (data.stories && data.stories.length) {
      wireList.innerHTML = data.stories.map((s, i) => {
        const isLoud = s.headline === s.headline.toUpperCase();
        return `
          <li class="wire-item">
            <div class="wire-category">${escapeHtml(s.category)}</div>
            <div class="wire-headline ${isLoud ? 'wire-headline--loud' : 'wire-headline--normal'}">
              <a href="${escapeAttr(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.headline)}</a>
            </div>
            <div class="wire-source">${escapeHtml(s.source)}</div>
          </li>
        `;
      }).join('');
    }
  }

  // --- Treadwell Corner ---
  function renderTreadwell(data) {
    if (!data.treadwellCorner || !data.treadwellCorner.length) return;
    const section = document.getElementById('treadwell-section');
    const list = document.getElementById('treadwell-list');
    list.innerHTML = data.treadwellCorner.map(item => `
      <li class="treadwell-item">
        <span class="treadwell-bullet" aria-hidden="true">&#x2767;</span>
        <div>
          <a href="${item.url}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.headline)}</a>
          <div class="treadwell-source">${escapeHtml(item.source || '')}</div>
        </div>
      </li>
    `).join('');
    section.style.display = 'block';
  }

  // --- Video of the Day ---
  function renderVideo(data) {
    if (!data.videoOfTheDay) return;
    const v = data.videoOfTheDay;
    if (!v.url) return;

    const section = document.getElementById('video-section');
    const label = document.getElementById('video-label');
    const embed = document.getElementById('video-embed');
    const caption = document.getElementById('video-caption');

    label.textContent = v.category || 'Video of the Day';
    if (v.caption) caption.textContent = v.caption;

    // YouTube
    const ytMatch = v.url.match(
      /(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([\w-]{11})/
    );
    if (ytMatch) {
      embed.innerHTML = `<iframe
        src="https://www.youtube.com/embed/${ytMatch[1]}?rel=0&modestbranding=1"
        title="${escapeHtml(v.title || 'Video of the Day')}"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowfullscreen loading="lazy"
      ></iframe>`;
      section.style.display = 'block';
      return;
    }

    // TikTok
    const ttMatch = v.url.match(/tiktok\.com\/@[^/]+\/video\/(\d+)/);
    if (ttMatch) {
      embed.innerHTML = `<blockquote class="tiktok-embed" cite="${escapeAttr(v.url)}" data-video-id="${ttMatch[1]}" style="max-width:605px;min-width:325px;">
        <section></section>
      </blockquote>`;
      const s = document.createElement('script');
      s.src = 'https://www.tiktok.com/embed.js';
      s.async = true;
      document.body.appendChild(s);
      section.style.display = 'block';
      return;
    }

    // X.com / Twitter
    const xMatch = v.url.match(/(?:twitter\.com|x\.com)\/\w+\/status\/(\d+)/);
    if (xMatch) {
      embed.innerHTML = `<blockquote class="twitter-tweet" data-dnt="true">
        <a href="${escapeAttr(v.url)}"></a>
      </blockquote>`;
      const s = document.createElement('script');
      s.src = 'https://platform.twitter.com/widgets.js';
      s.async = true;
      document.body.appendChild(s);
      section.style.display = 'block';
      return;
    }

    // Fallback: styled link card
    embed.innerHTML = `<a href="${escapeAttr(v.url)}" target="_blank" rel="noopener noreferrer" class="video-link-card">
      <span class="video-link-title">${escapeHtml(v.title || 'Watch Video')}</span>
      <span class="video-link-arrow">&#8594;</span>
    </a>`;
    section.style.display = 'block';
  }

  // --- Busey Easter Egg (1-in-5 chance) ---
  (function buseyEgg() {
    if (Math.random() > 0.2) return; // 80% chance of no Busey

    const egg = document.getElementById('busey-egg');
    if (!egg) return;

    // Pick a random edge position
    const positions = [
      // Right edge, random vertical
      () => ({ right: '12px', top: (15 + Math.random() * 60) + '%', left: 'auto', bottom: 'auto' }),
      // Left edge, random vertical
      () => ({ left: '12px', top: (20 + Math.random() * 55) + '%', right: 'auto', bottom: 'auto' }),
      // Bottom-right corner area
      () => ({ right: (10 + Math.random() * 40) + 'px', bottom: (20 + Math.random() * 60) + 'px', left: 'auto', top: 'auto' }),
      // Bottom-left corner area
      () => ({ left: (10 + Math.random() * 40) + 'px', bottom: (20 + Math.random() * 60) + 'px', right: 'auto', top: 'auto' }),
      // Peeking from the right side, mid-page
      () => ({ right: '-8px', top: (30 + Math.random() * 40) + '%', left: 'auto', bottom: 'auto' }),
    ];

    const pos = positions[Math.floor(Math.random() * positions.length)]();
    Object.assign(egg.style, pos);

    // Random slight rotation (-6 to +6 degrees)
    const tilt = (Math.random() * 12 - 6).toFixed(1);
    egg.querySelector('img').style.transform = 'rotate(' + tilt + 'deg)';

    // Reveal after a delay (Busey arrives late)
    egg.removeAttribute('hidden');
    setTimeout(() => egg.classList.add('active'), 2000 + Math.random() * 3000);
  })();

  // --- Helpers ---
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function escapeAttr(str) {
    return str.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function animateValue(el, start, end, duration) {
    const startTime = performance.now();
    function step(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const ease = 1 - Math.pow(1 - progress, 3);
      const current = start + (end - start) * ease;
      el.textContent = current.toFixed(1);
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

})();
