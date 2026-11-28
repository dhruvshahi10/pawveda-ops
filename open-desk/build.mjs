#!/usr/bin/env node
/**
 * PawVeda Open Desk — render kit.
 *
 *   node build.mjs specs/<id>.json            render one reel
 *   node build.mjs specs/<id>.json --frames   render, then also print where the 0 s / 1 s / 3 s frames are
 *
 * spec.json  ->  a HyperFrames composition (index.html)  ->  silent MP4 (HyperFrames)
 *            ->  procedural sound bed (ffmpeg, no samples, no AI)  ->  mux + loudness to -14 LUFS
 *            ->  ../media/<id>/reel.mp4  and  .build/<id>/frame-{0,1,3}s.jpg, cover.jpg
 *
 * The look (doc 44): a type panel on top (cream = the world, cocoa = the answer), the picture card below
 * with a slow camera push. Brand tokens and fonts from 03-VISUAL-SYSTEM. Reveals are wipes, never fade-ups
 * or bounces (03 §4, §7). Everything here is open source: HyperFrames (Apache 2.0), GSAP, ffmpeg,
 * Lexend / Fraunces / JetBrains Mono (OFL). Costs no credits.
 *
 * Picture source, in order: spec.footage (a real clip, e.g. from Dhruv's inbox) or spec.plate
 * (a path inside the factory repo; set FACTORY=/path/to/pawveda-content-factory, default ../../pawveda-content-factory).
 */
import { readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync, rmSync, statSync } from 'node:fs';
import { dirname, join, resolve, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync, spawnSync } from 'node:child_process';

const HERE = dirname(fileURLToPath(import.meta.url));
const OPS = resolve(HERE, '..');
const FACTORY = resolve(process.env.FACTORY || join(OPS, '..', 'pawveda-content-factory'));

const specPath = resolve(process.argv[2] || '');
if (!existsSync(specPath)) { console.error('usage: node build.mjs specs/<id>.json'); process.exit(1); }
const spec = JSON.parse(readFileSync(specPath, 'utf8'));
const { id, duration, beats } = spec;
if (!id || !duration || !Array.isArray(beats) || !beats.length) throw new Error('spec needs id, duration, beats');
if (duration > 14) throw new Error(`gate F5: ${duration}s is over 14 s`);
if (beats[0].eyebrow) throw new Error('gate F4: the question must be the first line at 0 s; no eyebrow on beat 0');

const W = 1080, H = 1920, PANEL = spec.panel || 760, FPS = 30;
const build = join(HERE, '.build', id);
rmSync(build, { recursive: true, force: true });
mkdirSync(build, { recursive: true });

/* ---------- picture ---------- */
let pictureTag;
if (spec.footage) {
  const src = resolve(dirname(specPath), spec.footage);
  copyFileSync(src, join(build, 'footage' + extname(src)));
  pictureTag = `<video id="pic" class="clip" src="footage${extname(src)}" data-start="0" data-duration="${duration}" muted playsinline></video>`;
} else {
  const src = join(FACTORY, spec.plate);
  if (!existsSync(src)) throw new Error(`plate not found: ${src} (is the factory repo cloned? set FACTORY=)`);
  copyFileSync(src, join(build, 'plate' + extname(src)));
  pictureTag = `<img id="pic" src="plate${extname(src)}" alt="">`;
}
const [fx, fy] = spec.focus || [50, 45];

/* ---------- type panel beats ---------- */
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const beatHtml = (b, i) => {
  const t0 = b.t, t1 = beats[i + 1]?.t ?? duration;
  const ground = b.ground === 'cocoa' ? 'cocoa' : 'cream';
  const parts = [];
  if (b.eyebrow) parts.push(`<div class="eyebrow r">${esc(b.eyebrow)}</div>`);
  if (b.badge) parts.push(`<div class="badge r band-${b.badge.band || 'neutral'}">${esc(b.badge.label)}</div>`);
  if (b.headline) parts.push(`<div class="headline ${b.size === 'hero' ? 'hero' : ''} r">${esc(b.headline)}</div>`);
  if (b.body) parts.push(`<div class="body r">${esc(b.body)}</div>`);
  if (b.foot) parts.push(`<div class="foot r">${esc(b.foot)}</div>`);
  return `<section id="b${i}" class="beat clip ${ground}" data-start="${t0}" data-duration="${(t1 - t0).toFixed(2)}">
    <div class="inner">${parts.join('\n')}</div>
    <div class="mark"><span class="dot"></span>PawVeda</div>
  </section>`;
};

const fonts = readFileSync(join(HERE, 'fonts.css'), 'utf8');
const gsapJs = readFileSync(join(HERE, 'node_modules/gsap/dist/gsap.min.js'), 'utf8');

const html = `<!doctype html>
<html lang="en" data-resolution="portrait"><head><meta charset="UTF-8">
<meta name="viewport" content="width=${W}, height=${H}">
<script>${gsapJs}</script>
<style>
${fonts}
:root{--terracotta:#CC785C;--cocoa-dark:#311D0E;--cream:#FAF8F2;--cream-hero:#FDF6E3;--ink:#1A1C1E;--ink-soft:#5C5348;
--sand:#EDE5D8;--ok:#2E7D32;--warn:#ED6C02;--danger:#D32F2F}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:${W}px;height:${H}px;overflow:hidden;background:var(--cream)}
#root{position:relative;width:${W}px;height:${H}px;overflow:hidden;background:var(--cream)}
.beat{position:absolute;left:0;top:0;width:${W}px;height:${PANEL + 60}px}
.beat.cream{background:var(--cream);color:var(--ink)}
.beat.cocoa{background:var(--cocoa-dark);color:var(--cream-hero)}
.inner{position:absolute;left:72px;right:72px;top:236px;display:flex;flex-direction:column;gap:22px}
.eyebrow{font:500 24px/1.15 "Lexend";letter-spacing:.08em;text-transform:uppercase;color:var(--terracotta)}
.cocoa .eyebrow{color:var(--cream-hero)}
.headline{font:600 72px/1.15 "Fraunces";letter-spacing:-.01em;max-width:30ch}
.headline.hero{font-size:104px}
.body{font:400 44px/1.4 "Lexend";max-width:32ch}
.foot{font:400 30px/1.5 "Lexend";color:var(--ink-soft)}
.cocoa .foot{color:var(--sand)}
.badge{align-self:flex-start;font:500 26px/1 "Lexend";letter-spacing:.06em;text-transform:uppercase;padding:14px 26px;border-radius:999px;color:var(--cream-hero);background:var(--terracotta)}
.band-danger{background:var(--danger)}.band-warn{background:var(--warn)}.band-ok{background:var(--ok)}
.mark{position:absolute;left:72px;top:${PANEL - 92}px;font:500 24px/1 "Lexend";display:flex;align-items:center;gap:12px;opacity:.9}
.dot{width:18px;height:18px;border-radius:50%;background:radial-gradient(circle at 35% 35%,#E39A80,var(--terracotta) 60%,#B86347)}
#card{position:absolute;left:0;top:${PANEL}px;width:${W}px;height:${H - PANEL}px;border-radius:44px 44px 0 0;overflow:hidden;background:var(--sand);z-index:5}
#pic{width:100%;height:100%;object-fit:cover;object-position:${fx}% ${fy}%;transform-origin:${fx}% ${fy}%}
</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="${duration}" data-width="${W}" data-height="${H}">
${beats.map(beatHtml).join('\n')}
<div id="card">${pictureTag}</div>
</div>
<script>
window.__timelines = window.__timelines || {};
const tl = gsap.timeline({ paused: true });
const push = ${JSON.stringify(spec.push || [1.0, 1.1])};
/* F6: visible camera move inside the first second, then a slow push for the rest. */
tl.fromTo('#pic', { scale: push[0], xPercent: 0 }, { scale: push[0] + 0.06, xPercent: ${(spec.drift ?? -1.5) / 2}, duration: 1.2, ease: 'power2.out' }, 0);
tl.to('#pic', { scale: push[1], xPercent: ${spec.drift ?? -1.5}, duration: ${duration} - 1.2, ease: 'none' }, 1.2);
/* Beat 0 is on screen from frame 1 (gate: the line lands at 0 s); later beats wipe in on their cut. */
${beats.map((b, i) => i === 0 ? '' : `tl.fromTo('#b${i} .r', { clipPath: 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0% 0 0)', duration: 0.38, ease: 'power2.out', stagger: 0.12 }, ${(b.t + 0.04).toFixed(2)});`).join('\n')}
window.__timelines['main'] = tl;
tl.seek(0);
</script>
</body></html>`;
writeFileSync(join(build, 'index.html'), html);
writeFileSync(join(build, 'hyperframes.json'), JSON.stringify({ name: id }, null, 2));

/* ---------- render (HyperFrames) ---------- */
const silent = join(build, 'silent.mp4');
const hf = join(HERE, 'node_modules/.bin/hyperframes');
execFileSync(hf, ['render', build, '-o', silent, '--fps', String(FPS), '--quality', 'delivery', '--quiet'], { stdio: 'inherit' });

/* ---------- sound bed: procedural, no samples ---------- */
const ticks = beats.map(b => b.t).filter(t => t > 0)
  .map(t => `0.45*sin(2*PI*1320*(t-${t}))*exp(-38*(t-${t}))*gte(t,${t})`).join('+') || '0';
const pad = '0.055*(sin(2*PI*110*t)+0.7*sin(2*PI*164.81*t)+0.5*sin(2*PI*220*t)+0.35*sin(2*PI*277.18*t))*(0.6+0.4*sin(2*PI*0.25*t))';
const thump = '0.7*sin(2*PI*72*t)*exp(-7*t)+0.35*sin(2*PI*1320*t)*exp(-38*t)';
const wav = join(build, 'bed.wav');
execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'lavfi', '-i',
  `aevalsrc='${pad}+${thump}+${ticks}':s=48000:d=${duration}`,
  '-af', `lowpass=f=5000,afade=t=in:d=0.02,afade=t=out:st=${duration - 0.7}:d=0.7,loudnorm=I=-14:TP=-1.5:LRA=7`,
  '-ar', '48000', '-ac', '2', wav]);

/* two-pass loudness: measure the bed, then set gain so the reel lands at -14 LUFS (24-QUALITY-BAR) */
const measure = (f) => { const r = require_spawn(f); const m = r.match(/I:\s+(-?[\d.]+) LUFS/g); return m ? parseFloat(m[m.length - 1].split(/\s+/)[1]) : null; };
function require_spawn(f) { return spawnSync('ffmpeg', ['-hide_banner','-nostats','-i', f, '-af','ebur128','-f','null','-']).stderr.toString(); }
{
  const raw = join(build, 'bed-raw.wav'); copyFileSync(wav, raw);
  let gain = 0;
  for (let k = 0; k < 4; k++) {
    const i = measure(wav);
    if (i === null || Math.abs(i + 14) <= 0.4) break;
    gain += (-14 - i);
    execFileSync('ffmpeg', ['-y','-loglevel','error','-i', raw, '-af', `volume=${gain.toFixed(2)}dB,alimiter=limit=0.72:level=false`, wav]);
  }
}

/* ---------- mux ---------- */
const outDir = join(OPS, 'media', id);
mkdirSync(outDir, { recursive: true });
const out = join(outDir, 'reel.mp4');
execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', silent, '-i', wav, '-map', '0:v:0', '-map', '1:a:0',
  '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-maxrate', '6M', '-bufsize', '12M', '-pix_fmt', 'yuv420p', '-r', String(FPS),
  '-c:a', 'aac', '-b:a', '160k', '-t', String(duration), '-movflags', '+faststart', out]);

/* ---------- frames for the gate (0 s, 1 s, 3 s) and a cover ---------- */
for (const s of [0, 1, 3]) {
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-ss', String(s === 0 ? 0.05 : s), '-i', out, '-frames:v', '1', '-q:v', '3', join(build, `frame-${s}s.jpg`)]);
}
execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-ss', String((spec.cover_ms ?? 600) / 1000), '-i', out, '-frames:v', '1', '-q:v', '2', join(build, 'cover.jpg')]);

const probe = execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration:stream=codec_name,width,height', '-of', 'json', out]).toString();
/* jsDelivr serves media to Instagram and refuses files over 20 MB; stay far under it. */
const mb = statSync(out).size / 1e6; if (mb > 12) throw new Error(`reel is ${mb.toFixed(1)} MB; keep under 12 MB for jsDelivr`);
console.log(JSON.stringify({ id, out, build, mb: +mb.toFixed(1), lufs: measure(out), probe: JSON.parse(probe) }, null, 1));
