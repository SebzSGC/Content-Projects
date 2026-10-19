import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { pathToFileURL } from "node:url";

/**
 * Emits a structured JSONL event to stdout.
 */
function emit(event) {
  process.stdout.write(JSON.stringify(event) + "\n");
}

/**
 * Spawns a child process with windowsHide: true enforced on Windows.
 */
export function hiddenSpawn(command, args = [], options = {}) {
  return spawn(command, args, {
    ...options,
    windowsHide: true,
    shell: false
  });
}

/**
 * Built-in GLSL transition shaders (MIT compatible, clean-room implementations).
 */
const GL_SHADERS = {
  crosswarp: `
    precision mediump float;
    varying vec2 uv;
    uniform sampler2D from, to;
    uniform float progress;
    void main() {
      float x = progress;
      x = smoothstep(0.0, 1.0, (x * 2.0 + uv.x - 1.0));
      vec2 p1 = (uv - 0.5) * (1.0 - x) + 0.5;
      vec2 p2 = (uv - 0.5) * x + 0.5;
      gl_FragColor = mix(texture2D(from, p1), texture2D(to, p2), x);
    }
  `,
  directionalwarp: `
    precision mediump float;
    varying vec2 uv;
    uniform sampler2D from, to;
    uniform float progress;
    void main() {
      vec2 direction = normalize(vec2(-1.0, 1.0));
      const float smoothness = 0.5;
      const vec2 center = vec2(0.5, 0.5);
      vec2 v = normalize(direction);
      v /= abs(v.x) + abs(v.y);
      float d = v.x * center.x + v.y * center.y;
      float m = 1.0 - smoothstep(-smoothness, 0.0, v.x * uv.x + v.y * uv.y - (d - 0.5 + progress * (1.0 + smoothness)));
      gl_FragColor = mix(texture2D(from, (uv - 0.5) * (1.0 - m) + 0.5), texture2D(to, (uv - 0.5) * m + 0.5), m);
    }
  `,
  swirl: `
    precision mediump float;
    varying vec2 uv;
    uniform sampler2D from, to;
    uniform float progress;
    void main() {
      vec2 p = uv - vec2(0.5);
      float dist = length(p);
      if (dist < 0.5) {
        float percent = (0.5 - dist) / 0.5;
        float A = (progress <= 0.5) ? mix(0.0, 1.0, progress / 0.5) : mix(1.0, 0.0, (progress - 0.5) / 0.5);
        float theta = percent * percent * A * 8.0 * 3.14159;
        float s = sin(theta);
        float c = cos(theta);
        p = vec2(dot(p, vec2(c, -s)), dot(p, vec2(s, c)));
      }
      p += vec2(0.5);
      gl_FragColor = mix(texture2D(from, p), texture2D(to, p), progress);
    }
  `,
  ripple: `
    precision mediump float;
    varying vec2 uv;
    uniform sampler2D from, to;
    uniform float progress;
    void main() {
      vec2 dir = uv - vec2(0.5);
      float dist = length(dir);
      vec2 offset = dir * (sin(progress * dist * 50.0 - progress * 25.0) + 0.5) / 30.0;
      gl_FragColor = mix(texture2D(from, uv + offset * (1.0 - progress)), texture2D(to, uv), smoothstep(0.2, 1.0, progress));
    }
  `
};

function buildGlTransitionHtml(shaderName) {
  const frag = GL_SHADERS[shaderName] || GL_SHADERS.crosswarp;
  return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>html,body{margin:0;padding:0;overflow:hidden;background:#000;}canvas{display:block;width:100vw;height:100vh;}</style></head>
<body><canvas id="c"></canvas>
<script>
const canvas = document.getElementById('c');
const gl = canvas.getContext('webgl', { preserveDrawingBuffer: true, alpha: false });
const vsSrc = 'attribute vec2 p; varying vec2 uv; void main(){ uv = p * 0.5 + 0.5; uv.y = 1.0 - uv.y; gl_Position = vec4(p, 0.0, 1.0); }';
const fsSrc = ${JSON.stringify(frag)};
function compile(type, src) {
  const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s;
}
const prog = gl.createProgram();
gl.attachShader(prog, compile(gl.VERTEX_SHADER, vsSrc));
gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, fsSrc));
gl.linkProgram(prog); gl.useProgram(prog);
const buf = gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER, buf);
gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, -1,1, 1,-1, 1,1]), gl.STATIC_DRAW);
const locP = gl.getAttribLocation(prog, 'p');
gl.enableVertexAttribArray(locP);
gl.vertexAttribPointer(locP, 2, gl.FLOAT, false, 0, 0);

function makeTex(unit) {
  const t = gl.createTexture();
  gl.activeTexture(gl.TEXTURE0 + unit);
  gl.bindTexture(gl.TEXTURE_2D, t);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  return t;
}
const texA = makeTex(0);
const texB = makeTex(1);
gl.uniform1i(gl.getUniformLocation(prog, 'from'), 0);
gl.uniform1i(gl.getUniformLocation(prog, 'to'), 1);
const locProg = gl.getUniformLocation(prog, 'progress');

function loadImg(url) {
  return new Promise((res, rej) => {
    const img = new Image();
    img.onload = () => res(img);
    img.onerror = rej;
    img.src = url;
  });
}

window.__renderGlFrame = async function(w, h, urlA, urlB, progress) {
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w; canvas.height = h; gl.viewport(0, 0, w, h);
  }
  const [imgA, imgB] = await Promise.all([loadImg(urlA), loadImg(urlB)]);
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, texA);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, imgA);
  gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, texB);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, imgB);
  gl.uniform1f(locProg, progress);
  gl.drawArrays(gl.TRIANGLES, 0, 6);
  gl.finish();
};
</script></body></html>`;
}

function buildFfmpegArgs(output, fpsFloat) {
  const { path: outPath, format, encoder } = output;
  const commonIn = ["-y", "-f", "image2pipe", "-vcodec", "png", "-r", String(fpsFloat), "-i", "-"];
  if (format === "webm_vp9_alpha") {
    return [
      ...commonIn,
      "-c:v", "libvpx-vp9",
      "-pix_fmt", "yuva420p",
      "-b:v", "0",
      "-crf", "28",
      "-row-mt", "1",
      "-auto-alt-ref", "0",
      "-metadata:s:v:0", "alpha_mode=1",
      outPath
    ];
  }
  const useNvenc = encoder === "h264_nvenc";
  const vCodec = useNvenc
    ? ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", "-pix_fmt", "yuv420p"]
    : ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p"];
  return [...commonIn, ...vCodec, "-movflags", "+faststart", outPath];
}

async function runRenderJob(req) {
  emit({ type: "ready", protocol: "vidforge.render/1", pid: process.pid });
  const puppeteer = await import("puppeteer-core");
  const fpsFloat = req.output.fps.num / req.output.fps.den;
  const width = req.output.width;
  const height = req.output.height;
  const workDir = req.runtime.work_dir;
  fs.mkdirSync(workDir, { recursive: true });
  fs.mkdirSync(path.dirname(req.output.path), { recursive: true });

  const browser = await puppeteer.default.launch({
    executablePath: req.runtime.chrome_path,
    headless: true,
    defaultViewport: { width, height, deviceScaleFactor: 1 },
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-gpu-sandbox",
      "--enable-webgl",
      "--ignore-gpu-blocklist",
      "--allow-file-access-from-files",
      "--hide-scrollbars",
      "--mute-audio"
    ]
  });

  try {
    const page = await browser.newPage();
    const client = await page.createCDPSession();

    const ffArgs = buildFfmpegArgs(req.output, fpsFloat);
    const ff = hiddenSpawn(req.runtime.ffmpeg_path, ffArgs, {
      cwd: workDir,
      stdio: ["pipe", "ignore", "pipe"]
    });
    let ffErr = "";
    ff.stderr.on("data", (d) => { ffErr += d.toString(); });

    const writeFrame = (buf) =>
      new Promise((resolve, reject) => {
        const ok = ff.stdin.write(buf, (err) => (err ? reject(err) : resolve()));
        if (!ok) ff.stdin.once("drain", resolve);
      });

    if (req.task.kind === "template") {
      await client.send("Emulation.setDefaultBackgroundColorOverride", {
        color: { r: 0, g: 0, b: 0, a: req.output.format === "webm_vp9_alpha" ? 0 : 255 }
      });
      const entryUrl = pathToFileURL(path.join(req.task.template_dir, "index.html")).href;
      await page.goto(entryUrl, { waitUntil: "networkidle0" });
      await page.evaluate(
        async (props, canvas) => {
          if (document.fonts && document.fonts.ready) await document.fonts.ready;
          await window.__vf.init({ ...props, duration_us: props.duration_us }, canvas);
        },
        { ...req.task.props, duration_us: req.task.duration_us },
        { width, height, fps: fpsFloat }
      );

      const durationMs = req.task.duration_us / 1000;
      const totalFrames = Math.max(1, Math.round((req.task.duration_us / 1_000_000) * fpsFloat));
      for (let i = 0; i < totalFrames; i++) {
        const tMs = (i / Math.max(1, totalFrames - 1)) * durationMs;
        await page.evaluate((t) => window.__vf.seek(t), tMs);
        const buf = await page.screenshot({ type: "png", omitBackground: req.output.format === "webm_vp9_alpha" });
        await writeFrame(buf);
        if (i % 5 === 0 || i === totalFrames - 1) {
          emit({ type: "progress", frame: i + 1, total: totalFrames, phase: "capture" });
        }
      }
    } else if (req.task.kind === "gl_transition") {
      const htmlPath = path.join(workDir, "_gl_runner.html");
      fs.writeFileSync(htmlPath, buildGlTransitionHtml(req.task.transition), "utf-8");
      await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
      const totalFrames = req.task.frame_count;
      const filesA = fs.readdirSync(req.task.frames_a_dir).filter(f => f.endsWith(".png")).sort();
      const filesB = fs.readdirSync(req.task.frames_b_dir).filter(f => f.endsWith(".png")).sort();

      for (let i = 0; i < totalFrames; i++) {
        const fileA = path.join(req.task.frames_a_dir, filesA[Math.min(i, filesA.length - 1)]);
        const fileB = path.join(req.task.frames_b_dir, filesB[Math.min(i, filesB.length - 1)]);
        const progress = totalFrames > 1 ? i / (totalFrames - 1) : 1.0;
        await page.evaluate(
          (w, h, uA, uB, p) => window.__renderGlFrame(w, h, uA, uB, p),
          width,
          height,
          pathToFileURL(fileA).href,
          pathToFileURL(fileB).href,
          progress
        );
        const buf = await page.screenshot({ type: "png" });
        await writeFrame(buf);
        emit({ type: "progress", frame: i + 1, total: totalFrames, phase: "gl_transition" });
      }
    }

    ff.stdin.end();
    const exitCode = await new Promise((res) => ff.on("close", res));
    if (exitCode !== 0) {
      throw new Error(`FFmpeg exited with code ${exitCode}: ${ffErr.slice(-600)}`);
    }

    const fileBuf = fs.readFileSync(req.output.path);
    const sha256 = crypto.createHash("sha256").update(fileBuf).digest("hex");
    emit({
      type: "complete",
      output: req.output.path,
      sha256
    });
  } finally {
    await browser.close();
  }
}

async function main() {
  const args = process.argv.slice(2);
  const reqIdx = args.indexOf("--request");
  if (reqIdx === -1 || !args[reqIdx + 1]) {
    emit({ type: "error", code: "MISSING_ARG", message: "Use --request <path>", retryable: false });
    process.exit(2);
  }
  try {
    const raw = fs.readFileSync(args[reqIdx + 1], "utf-8");
    const req = JSON.parse(raw);
    await runRenderJob(req);
  } catch (err) {
    emit({
      type: "error",
      code: "RENDER_FAILED",
      message: err?.message || String(err),
      retryable: false
    });
    process.exit(1);
  }
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
