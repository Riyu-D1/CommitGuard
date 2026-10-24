/* orb.js — vanilla driver for the thinking-orbs engine (thinking-orbs.js).
 *
 *   const orb = mountOrb(canvas, { state: 'listening', size: 208 });
 *   orb.setState('solving');   // switch animation
 *   orb.setSize(160);          // re-render at a new CSS size
 *   orb.destroy();             // stop the rAF loop
 *
 * Mirrors src/ThinkingOrb.tsx: one rAF loop per orb, DPR-aware canvas,
 * pauses offscreen (IntersectionObserver) and on hidden tabs, and draws a
 * single deterministic frame for prefers-reduced-motion.
 *
 * Sizes beyond the tuned 64px preset keep the 64-preset dot density by
 * scaling the lattice/count opts quadratically (the same keys the engine's
 * internal scaleCounts uses), so a 208px hero reads as the same orb, not a
 * sparse one.
 */
(function () {
  'use strict';
  var T = window.ThinkingOrbs;

  var COUNT_PAIRS = [['latRings', 'lonDensity'], ['rings', 'lonDensity'], ['lanes', 'segs']];
  var COUNT_KEYS = ['orbitN', 'ghostN', 'nodeN', 'strandN', 'signals'];

  function scaleCounts(opts, scale) {
    var done = {};
    var rt = Math.sqrt(scale);
    COUNT_PAIRS.forEach(function (pair) {
      var a = pair[0], b = pair[1];
      if (opts[a] != null && opts[b] != null && !done[a] && !done[b]) {
        opts[a] = Math.max(2, Math.round(opts[a] * rt));
        opts[b] = Math.max(2, Math.round(opts[b] * rt));
        done[a] = done[b] = true;
      }
    });
    COUNT_KEYS.forEach(function (k) {
      var v = opts[k];
      if (v != null && v !== 0 && !done[k]) opts[k] = Math.max(1, Math.round(v * scale));
    });
    if (opts.iconD != null) opts.iconD = Math.max(0.02, opts.iconD * scale);
    return opts;
  }

  function mountOrb(canvas, opts) {
    opts = opts || {};
    var state = opts.state || 'breathing';
    var size = opts.size || 64;
    var speedMul = opts.speed || 1;
    var dark = opts.dark !== false;
    var ctx = canvas.getContext('2d');
    var raf = 0;
    var running = false;
    var visible = true;
    var resolved = null;
    var reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

    function resolve() {
      var presetSize = size <= 32 ? 20 : 64;
      var r = T.resolvePreset(state, presetSize);
      var o = r.opts;
      if (size > 80) {
        var d = size / 64;
        o = scaleCounts({ ...o }, Math.min(8, d * d));
      }
      resolved = { mode: r.mode, speed: r.speed * speedMul, opts: o };
    }

    function resize() {
      var dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(size * dpr);
      canvas.height = Math.round(size * dpr);
      canvas.style.width = size + 'px';
      canvas.style.height = size + 'px';
      resolve();
    }

    function frame(tSec) {
      var dpr = canvas.width / size;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);
      T.MODE_DRAWS[resolved.mode](ctx, size, tSec, dark, resolved.opts);
    }

    function loop() {
      frame((performance.now() / 1000) * resolved.speed);
      if (running) raf = requestAnimationFrame(loop);
    }
    function start() {
      if (running) return;
      running = true;
      raf = requestAnimationFrame(loop);
    }
    function stop() {
      running = false;
      cancelAnimationFrame(raf);
    }

    resize();

    var io = null;
    var onVis = null;
    if (reduced) {
      frame(0.6);
    } else {
      frame((performance.now() / 1000) * resolved.speed);
      if ('IntersectionObserver' in window) {
        io = new IntersectionObserver(function (entries) {
          visible = entries[0].isIntersecting;
          if (visible && document.visibilityState !== 'hidden') start();
          else stop();
        });
        io.observe(canvas);
      }
      onVis = function () {
        if (document.visibilityState === 'hidden') stop();
        else if (visible) start();
      };
      document.addEventListener('visibilitychange', onVis);
      if (!io) start();
    }

    return {
      setState: function (s) {
        if (s === state) return;
        state = s;
        resolve();
        if (reduced || !running) frame(0.6);
      },
      setSize: function (px) {
        if (px === size) return;
        size = px;
        resize();
      },
      getState: function () { return state; },
      destroy: function () {
        stop();
        if (io) io.disconnect();
        if (onVis) document.removeEventListener('visibilitychange', onVis);
      }
    };
  }

  window.mountOrb = mountOrb;
})();
