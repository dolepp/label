(() => {
  "use strict";

  const WIDTH = 1920;
  const HEIGHT = 1080;

  function supportedMimeType() {
    if (!window.MediaRecorder || !HTMLCanvasElement.prototype.captureStream || !(window.AudioContext || window.webkitAudioContext)) return null;
    return [
      "video/mp4;codecs=avc1.42001f,mp4a.40.2",
      "video/mp4",
      "video/webm;codecs=vp8,opus",
      "video/webm",
    ].find((type) => MediaRecorder.isTypeSupported(type)) || null;
  }

  function activePosition(lines, time) {
    let low = 0;
    let high = lines.length - 1;
    let candidate = -1;
    while (low <= high) {
      const middle = (low + high) >> 1;
      if (lines[middle].begin <= time) {
        candidate = middle;
        low = middle + 1;
      } else high = middle - 1;
    }
    return { candidate, active: candidate >= 0 && time <= lines[candidate].end ? candidate : -1 };
  }

  function createRenderer(canvas, options) {
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Не удалось подготовить изображение видео.");
    const cache = new Map();
    const fontFamily = 'Arial, sans-serif';
    const scale = Math.max(0.7, Math.min(1.6, Number(options.fontScale) || 1));
    const background = ctx.createLinearGradient(0, 0, WIDTH, HEIGHT);
    background.addColorStop(0, "#16102c");
    background.addColorStop(0.5, "#05070d");
    background.addColorStop(1, "#071a28");

    function textFit(text, x, y, maxWidth, size, color, weight = 700) {
      ctx.font = `${weight} ${size}px ${fontFamily}`;
      ctx.fillStyle = color;
      const letters = Array.from(text);
      let label = text;
      while (letters.length && ctx.measureText(label).width > maxWidth) {
        letters.pop();
        label = letters.join("") + "…";
      }
      ctx.fillText(label, x, y);
    }

    function wrap(line, fontSize, secondary) {
      ctx.font = `${secondary ? 600 : 800} ${fontSize}px ${fontFamily}`;
      const maxWidth = 1696;
      const space = ctx.measureText(" ").width;
      const words = secondary ? [{ text: line.text }] : line.words;
      const rows = [{ width: 0, runs: [] }];
      for (const word of words) {
        for (const token of word.text.split(/\s+/).filter(Boolean)) {
          // Break exceptionally long unspaced text without cutting a surrogate pair.
          let parts = [token];
          if (ctx.measureText(token).width > maxWidth) {
            parts = [];
            let part = "";
            for (const letter of Array.from(token)) {
              if (part && ctx.measureText(part + letter).width > maxWidth) { parts.push(part); part = ""; }
              part += letter;
            }
            if (part) parts.push(part);
          }
          for (const text of parts) {
            const width = ctx.measureText(text).width;
            let row = rows[rows.length - 1];
            if (row.runs.length && row.width + space + width > maxWidth) {
              row = { width: 0, runs: [] };
              rows.push(row);
            }
            const gap = row.runs.length ? space : 0;
            row.runs.push({ text, width, gap, begin: word.begin, end: word.end });
            row.width += gap + width;
          }
        }
      }
      return rows;
    }

    function layout(index, secondary) {
      const key = `${index}:${secondary}`;
      if (cache.has(key)) return cache.get(key);
      const line = options.lines[index];
      let size = secondary ? Math.min(48, 36 * scale) : Math.min(104, 82 * scale);
      let rows = wrap(line, size, secondary);
      const maxHeight = secondary ? 120 : 390;
      while (size > 24 && rows.length * size * 1.24 > maxHeight) {
        size -= 2;
        rows = wrap(line, size, secondary);
      }
      const result = { rows, size, height: rows.length * size * 1.24 };
      cache.set(key, result);
      return result;
    }

    function drawLine(index, centerY, time, secondary = false) {
      if (index < 0 || index >= options.lines.length) return;
      const item = layout(index, secondary);
      ctx.font = `${secondary ? 600 : 800} ${item.size}px ${fontFamily}`;
      ctx.textBaseline = "middle";
      let y = centerY - item.height / 2 + item.size * 0.62;
      for (const row of item.rows) {
        let x = (WIDTH - row.width) / 2;
        for (const run of row.runs) {
          x += run.gap;
          ctx.fillStyle = secondary ? "#64748b" : time >= run.end ? "#f8fafc" : time >= run.begin ? "#38bdf8" : "#64748b";
          ctx.fillText(run.text, x, y);
          x += run.width;
        }
        y += item.size * 1.24;
      }
    }

    return (audioTime) => {
      const time = audioTime + options.offset;
      ctx.fillStyle = background;
      ctx.fillRect(0, 0, WIDTH, HEIGHT);
      ctx.save();
      ctx.beginPath();
      ctx.roundRect(64, 48, 120, 120, 18);
      ctx.clip();
      ctx.fillStyle = "#172033";
      ctx.fillRect(64, 48, 120, 120);
      if (options.cover) {
        const side = Math.min(options.cover.naturalWidth, options.cover.naturalHeight);
        ctx.drawImage(options.cover, (options.cover.naturalWidth - side) / 2, (options.cover.naturalHeight - side) / 2, side, side, 64, 48, 120, 120);
      } else {
        ctx.fillStyle = "#7dd3fc";
        ctx.font = `600 66px ${fontFamily}`;
        ctx.textBaseline = "middle";
        ctx.fillText("♫", 99, 108);
      }
      ctx.restore();
      ctx.textBaseline = "middle";
      textFit(options.artist || "Исполнитель", 214, 80, 1638, 30, "#a5b4fc", 600);
      textFit(options.title || "Название трека", 214, 130, 1638, 46, "#f8fafc", 800);
      ctx.fillStyle = "#334155";
      ctx.fillRect(64, 205, 1792, 1);

      const position = activePosition(options.lines, time);
      const current = position.active;
      ctx.save();
      // Mirror the lyrics only, matching the interactive teleprompter.
      if (options.mirror) { ctx.translate(WIDTH, 0); ctx.scale(-1, 1); }
      if (current >= 0) {
        const currentHeight = layout(current, false).height;
        drawLine(current - 1, Math.max(290, 600 - currentHeight / 2 - 110), time, true);
        drawLine(current, 600, time);
        drawLine(current + 1, Math.min(944, 600 + currentHeight / 2 + 110), time, true);
      } else {
        drawLine(position.candidate, 382, time, true);
        drawLine(position.candidate + 1, 794, time, true);
      }
      ctx.restore();
    };
  }

  async function exportVideo(options) {
    const mimeType = supportedMimeType();
    if (!mimeType) throw new Error("Браузер не поддерживает сохранение видео. Откройте суфлёр в актуальном Chrome, Edge или Safari.");
    if (options.signal?.aborted) throw new DOMException("Отменено", "AbortError");
    const canvas = document.createElement("canvas");
    canvas.width = WIDTH;
    canvas.height = HEIGHT;
    // Keep capture and animation active even though the export has its own canvas.
    canvas.className = "tp-export-canvas";
    canvas.setAttribute("aria-hidden", "true");
    (options.previewHost || document.body).prepend(canvas);
    if (!options.previewHost) Object.assign(canvas.style, { position: "fixed", right: "16px", bottom: "16px", width: "320px", zIndex: "15000" });
    const exportAudio = new Audio(options.audioUrl);
    exportAudio.preload = "auto";
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    let context;
    let source;
    let destination;
    let stream;
    let recorder;
    let frame = null;
    let cleanupListeners = () => {};
    const chunks = [];
    try {
      context = new AudioContextClass();
      // Resume in the click gesture, before any asynchronous font/media loading.
      await context.resume();
      await new Promise((resolve, reject) => {
        if (exportAudio.readyState >= 3) { resolve(); return; }
        let timer;
        const cleanup = () => {
          clearTimeout(timer);
          exportAudio.removeEventListener("canplay", ready);
          exportAudio.removeEventListener("error", fail);
          options.signal?.removeEventListener("abort", abort);
        };
        const ready = () => { cleanup(); resolve(); };
        const fail = () => { cleanup(); reject(new Error("Не удалось подготовить аудио для видео.")); };
        const abort = () => { cleanup(); reject(new DOMException("Отменено", "AbortError")); };
        exportAudio.addEventListener("canplay", ready, { once: true });
        exportAudio.addEventListener("error", fail, { once: true });
        options.signal?.addEventListener("abort", abort, { once: true });
        timer = window.setTimeout(fail, 15000);
        if (options.signal?.aborted) abort();
      });
      source = context.createMediaElementSource(exportAudio);
      destination = context.createMediaStreamDestination();
      source.connect(destination);
      if (document.fonts?.ready) await document.fonts.ready;
      const draw = createRenderer(canvas, options);
      draw(0);
      stream = canvas.captureStream(30);
      const videoTrack = stream.getVideoTracks()[0];
      destination.stream.getAudioTracks().forEach((track) => stream.addTrack(track));
      recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 8000000, audioBitsPerSecond: 192000 });
      await new Promise((resolve, reject) => {
        let failure = null;
        let stopping = false;
        const stop = (error = null) => {
          if (stopping) return;
          stopping = true;
          failure = error;
          exportAudio.pause();
          if (frame !== null) cancelAnimationFrame(frame);
          if (recorder.state !== "inactive") recorder.stop();
          else if (error) reject(error);
        };
        const abort = () => stop(new DOMException("Отменено", "AbortError"));
        const visibility = () => {
          if (document.hidden) stop(new Error("Подготовка остановлена: вкладка была скрыта. Повторите скачивание и держите вкладку открытой."));
        };
        cleanupListeners = () => {
          options.signal?.removeEventListener("abort", abort);
          document.removeEventListener("visibilitychange", visibility);
        };
        options.signal?.addEventListener("abort", abort, { once: true });
        document.addEventListener("visibilitychange", visibility);
        recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
        recorder.onerror = () => stop(new Error("Не удалось сохранить видео. Попробуйте ещё раз."));
        recorder.onstop = () => {
          cleanupListeners();
          if (failure) reject(failure);
          else resolve();
        };
        exportAudio.onerror = () => stop(new Error("Не удалось прочитать аудиотрек для видео."));
        exportAudio.onended = () => stop();
        const tick = () => {
          if (stopping) return;
          try {
            draw(exportAudio.currentTime);
            videoTrack.requestFrame?.();
            options.onProgress?.(Math.min(99, exportAudio.currentTime / options.duration * 100), exportAudio.currentTime);
            frame = requestAnimationFrame(tick);
          } catch (error) { stop(error); }
        };
        if (options.signal?.aborted) { reject(new DOMException("Отменено", "AbortError")); return; }
        try {
          recorder.start(1000);
          tick();
          exportAudio.play().catch((error) => stop(new Error(`Не удалось начать подготовку видео: ${error.message}`)));
        } catch (error) { stop(error); }
      });
      const type = recorder.mimeType || mimeType;
      const blob = new Blob(chunks, { type });
      if (!blob.size) throw new Error("Видео получилось пустым. Попробуйте ещё раз.");
      options.onProgress?.(100, options.duration);
      return { blob, extension: type.startsWith("video/mp4") ? "mp4" : "webm" };
    } finally {
      cleanupListeners();
      if (frame !== null) cancelAnimationFrame(frame);
      exportAudio.pause();
      exportAudio.removeAttribute("src");
      exportAudio.load();
      if (recorder && recorder.state !== "inactive") recorder.stop();
      stream?.getTracks().forEach((track) => track.stop());
      destination?.stream.getTracks().forEach((track) => track.stop());
      source?.disconnect();
      if (context && context.state !== "closed") await context.close().catch(() => {});
      canvas.remove();
    }
  }

  window.TeleprompterExport = { supported: () => Boolean(supportedMimeType()), exportVideo };
})();
