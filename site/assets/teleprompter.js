(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const tool = byId("teleprompterTool");
  const openButton = byId("teleprompterServiceBtn");
  if (!tool || !openButton) return;

  const setup = byId("tpSetup");
  const stage = byId("tpStage");
  const audio = byId("tpAudio");
  const audioInput = byId("tpAudioInput");
  const ttmlInput = byId("tpTtmlInput");
  const plainText = byId("tpPlainText");
  let plainMode = false;
  let textLoadVersion = 0;
  const audioZone = byId("tpAudioZone");
  const ttmlZone = byId("tpTtmlZone");
  const audioName = byId("tpAudioName");
  const ttmlName = byId("tpTtmlName");
  const setupStatus = byId("tpSetupStatus");
  const startButton = byId("tpStartBtn");
  const playButton = byId("tpPlayBtn");
  const seek = byId("tpSeek");
  const timeLabel = byId("tpTimeLabel");
  const offsetRange = byId("tpOffsetRange");
  const offsetValue = byId("tpOffsetValue");
  const fontScale = byId("tpFontScale");
  const mirrorButton = byId("tpMirrorBtn");
  const fullscreenButton = byId("tpFullscreenBtn");
  const previousLine = byId("tpPreviousLine");
  const currentLine = byId("tpCurrentLine");
  const nextLine = byId("tpNextLine");
  const lyricsWrap = byId("tpLyricsWrap");
  const trackTitle = byId("tpTrackTitle");
  const artistName = byId("tpArtistName");
  const artistInput = byId("tpArtistInput");
  const titleInput = byId("tpTitleInput");
  const coverInput = byId("tpCoverInput");
  const coverZone = byId("tpCoverZone");
  const coverPreview = byId("tpCoverPreview");
  const stageCover = byId("tpStageCover");
  const downloadButton = byId("tpDownloadBtn");
  const exportPanel = byId("tpExportPanel");
  const exportStatus = byId("tpExportStatus");
  const exportProgress = byId("tpExportProgress");
  const exportCancelButton = byId("tpExportCancelBtn");
  const exportSaveLink = byId("tpExportSaveLink");
  let coverImage = null;
  let coverUrl = null;
  let coverLoadVersion = 0;
  let automaticTitle = "";
  let exportController = null;
  let exportUrl = null;

  let lines = [];
  let audioFile = null;
  let audioReady = false;
  let audioUrl = null;
  let currentLineIndex = null;
  let animationFrame = null;
  let hideTimer = null;

  function setStatus(message, kind = "") {
    setupStatus.textContent = message;
    setupStatus.className = `tp-status${kind ? ` is-${kind}` : ""}`;
  }

  function parseTime(raw, rates) {
    if (raw === null || raw === undefined) return null;
    const value = String(raw).trim();
    if (!value) return null;

    const metric = value.match(/^(\d+(?:\.\d+)?)(h|m|s|ms|f|t)$/);
    if (metric) {
      const amount = Number(metric[1]);
      const unit = metric[2];
      if (unit === "h") return amount * 3600;
      if (unit === "m") return amount * 60;
      if (unit === "s") return amount;
      if (unit === "ms") return amount / 1000;
      if (unit === "f") return amount / rates.frameRate;
      if (unit === "t") return amount / rates.tickRate;
    }

    const parts = value.split(":");
    if (parts.length === 1) {
      const seconds = Number(parts[0]);
      return Number.isFinite(seconds) ? seconds : null;
    }
    const numbers = parts.map(Number);
    if (numbers.some((part) => !Number.isFinite(part))) return null;
    if (numbers.length === 2) return numbers[0] * 60 + numbers[1];
    if (numbers.length === 3) return numbers[0] * 3600 + numbers[1] * 60 + numbers[2];
    if (numbers.length === 4) {
      return numbers[0] * 3600 + numbers[1] * 60 + numbers[2] + numbers[3] / rates.frameRate;
    }
    return null;
  }

  function timingRates(documentNode) {
    const root = documentNode.documentElement;
    const attributes = Array.from(root?.attributes || []);
    const read = (localName, fallback) => {
      const attribute = attributes.find((item) => item.localName === localName);
      const value = Number(attribute?.value);
      return Number.isFinite(value) && value > 0 ? value : fallback;
    };
    const frameRate = read("frameRate", 25);
    return { frameRate, tickRate: read("tickRate", frameRate) };
  }

  function parseTtml(xmlText) {
    const documentNode = new DOMParser().parseFromString(xmlText, "application/xml");
    if (documentNode.querySelector("parsererror")) {
      throw new Error("Не удалось прочитать TTML.");
    }

    const rates = timingRates(documentNode);
    const paragraphs = Array.from(documentNode.getElementsByTagName("*"))
      .filter((element) => element.localName === "p");
    const parsed = [];

    paragraphs.forEach((paragraph) => {
      const begin = parseTime(paragraph.getAttribute("begin"), rates);
      let end = parseTime(paragraph.getAttribute("end"), rates);
      const duration = parseTime(paragraph.getAttribute("dur"), rates);
      if (begin === null) return;
      if (end === null && duration !== null) end = begin + duration;

      const spans = Array.from(paragraph.getElementsByTagName("*"))
        .filter((element) => element.localName === "span" && element.hasAttribute("begin"));
      const words = spans.map((span) => {
        const wordBegin = parseTime(span.getAttribute("begin"), rates);
        let wordEnd = parseTime(span.getAttribute("end"), rates);
        const wordDuration = parseTime(span.getAttribute("dur"), rates);
        if (wordEnd === null && wordDuration !== null && wordBegin !== null) wordEnd = wordBegin + wordDuration;
        return {
          text: (span.textContent || "").replace(/\s+/g, " ").trim(),
          begin: wordBegin,
          end: wordEnd,
        };
      }).filter((word) => word.text && word.begin !== null);

      const text = words.length
        ? words.map((word) => word.text).join(" ")
        : (paragraph.textContent || "").replace(/\s+/g, " ").trim();
      if (!text) return;
      parsed.push({ begin, end, text, words });
    });

    parsed.sort((left, right) => left.begin - right.begin);
    parsed.forEach((line, lineIndex) => {
      if (line.end === null) line.end = parsed[lineIndex + 1]?.begin ?? line.begin + 2;
      if (!line.words.length) {
        line.words = [{ text: line.text, begin: line.begin, end: line.end }];
        return;
      }
      line.words.forEach((word, wordIndex) => {
        if (word.end === null) word.end = line.words[wordIndex + 1]?.begin ?? line.end;
      });
    });
    return parsed;
  }

  function applyPlainText() {
    const texts = plainText.value.replace(/^\uFEFF/, "").split(/\r?\n/).map((text) => text.trim()).filter(Boolean);
    const duration = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 0;
    lines = texts.map((text, index) => {
      const begin = duration * index / texts.length;
      const end = duration * (index + 1) / texts.length;
      return { text, begin, end, words: [{ text, begin, end }] };
    });
    currentLineIndex = null;
    updateReadyState();
  }

  function updateReadyState() {
    const ready = Boolean(audioFile && audioReady && lines.length && Number.isFinite(audio.duration) && audio.duration > 0);
    startButton.disabled = !ready;
    if (plainMode && !lines.length) setStatus("Введите текст или загрузите файл.");
    else if (audioFile && lines.length && !ready) setStatus("Ожидаем длительность аудио…");
    if (ready) {
      setStatus(`${lines.length} строк готово к воспроизведению.${plainMode ? " Строки распределены равномерно." : ""}`, "ready");
    }
  }

  function loadAudioFile(file) {
    if (!file || (!file.type.startsWith("audio/") && !/\.(mp3|wav|m4a|ogg|flac|aac)$/i.test(file.name))) {
      setStatus("Выберите аудиофайл.", "error");
      return;
    }
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    audioReady = false;
    audioFile = file;
    audioUrl = URL.createObjectURL(file);
    audio.src = audioUrl;
    audioName.textContent = file.name;
    const fileTitle = file.name.replace(/\.[^.]+$/, "");
    if (!titleInput.value.trim() || titleInput.value === automaticTitle) titleInput.value = fileTitle;
    automaticTitle = fileTitle;
    updateTrackMetadata();
    audioZone.classList.add("is-loaded");
    updateReadyState();
  }

  function updateTrackMetadata() {
    artistName.textContent = artistInput.value.trim() || "Исполнитель";
    trackTitle.textContent = titleInput.value.trim() || automaticTitle || "Название трека";
  }

  function clearCover() {
    coverLoadVersion++;
    if (coverUrl) URL.revokeObjectURL(coverUrl);
    coverUrl = null;
    coverImage = null;
    coverInput.value = "";
    coverPreview.removeAttribute("src");
    stageCover.removeAttribute("src");
    coverPreview.classList.add("hidden");
    stageCover.classList.add("hidden");
    byId("tpCoverPlaceholder").classList.remove("hidden");
    byId("tpCoverName").textContent = "JPG, PNG или WEBP · необязательно";
    coverZone.classList.remove("is-loaded");
  }

  async function loadCoverFile(file) {
    if (!file || !/\.(jpe?g|png|webp)$/i.test(file.name)) {
      setStatus("Выберите обложку JPG, PNG или WEBP.", "error");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setStatus("Обложка должна быть не больше 10 МБ.", "error");
      return;
    }
    const version = ++coverLoadVersion;
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.src = url;
    try {
      await image.decode();
      if (version !== coverLoadVersion) { URL.revokeObjectURL(url); return; }
      if (coverUrl) URL.revokeObjectURL(coverUrl);
      coverUrl = url;
      coverImage = image;
      coverPreview.src = url;
      stageCover.src = url;
      coverPreview.classList.remove("hidden");
      stageCover.classList.remove("hidden");
      byId("tpCoverPlaceholder").classList.add("hidden");
      byId("tpCoverName").textContent = file.name;
      coverZone.classList.add("is-loaded");
      updateReadyState();
    } catch (_) {
      URL.revokeObjectURL(url);
      if (version === coverLoadVersion) setStatus("Не удалось прочитать обложку.", "error");
    }
  }

  function cancelExport() {
    exportController?.abort();
  }

  function setExporting(active) {
    stage.classList.toggle("is-exporting", active);
    [downloadButton, playButton, seek, offsetRange, fontScale, mirrorButton, byId("tpHideBtn")].forEach((button) => { button.disabled = active; });
    exportCancelButton.classList.toggle("hidden", !active);
    showControls();
  }

  async function downloadVideo() {
    if (exportController || startButton.disabled) return;
    audio.pause();
    stopAnimation();
    updateTrackMetadata();
    exportPanel.classList.remove("hidden");
    exportSaveLink.classList.add("hidden");
    if (exportUrl) URL.revokeObjectURL(exportUrl);
    exportUrl = null;
    exportProgress.value = 0;
    if (!window.TeleprompterExport?.supported()) {
      exportStatus.textContent = "Браузер не поддерживает сохранение видео. Попробуйте актуальный Chrome, Edge или Safari.";
      exportCancelButton.classList.add("hidden");
      return;
    }
    exportController = new AbortController();
    setExporting(true);
    exportStatus.textContent = "Готовим видео 1920×1080. Подготовка занимает время трека; держите вкладку открытой.";
    try {
      const result = await window.TeleprompterExport.exportVideo({
        audioUrl, duration: audio.duration, cover: coverImage, previewHost: exportPanel,
        artist: artistName.textContent, title: trackTitle.textContent,
        lines: lines.map((line) => ({ ...line, words: line.words.map((word) => ({ ...word })) })),
        fontScale: fontScale.value, offset: Number(offsetRange.value) || 0,
        mirror: lyricsWrap.classList.contains("is-mirrored"), signal: exportController.signal,
        onProgress: (progress, time) => {
          exportProgress.value = progress;
          if (Number.isFinite(time)) renderPosition(time + (Number(offsetRange.value) || 0));
          exportStatus.textContent = `Готовим видео 1920×1080: ${Math.floor(progress)}%. Держите вкладку открытой.`;
        },
      });
      exportUrl = URL.createObjectURL(result.blob);
      const filename = `${artistInput.value.trim() ? `${artistInput.value.trim()} — ` : ""}${trackTitle.textContent}`
        .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_").slice(0, 120);
      exportSaveLink.href = exportUrl;
      exportSaveLink.download = `${filename || "Суфлер"}_1080p.${result.extension}`;
      exportSaveLink.classList.remove("hidden");
      exportStatus.textContent = `Видео 1920×1080 готово · ${result.extension.toUpperCase()} · ${(result.blob.size / 1024 / 1024).toFixed(1)} МБ.`;
      // A manual save link remains available if the browser blocks automatic download.
      exportSaveLink.click();
    } catch (error) {
      exportStatus.textContent = error.name === "AbortError" ? "Подготовка видео отменена." : error.message || "Не удалось подготовить видео.";
    } finally {
      exportController = null;
      setExporting(false);
      tick();
    }
  }

  function loadTtmlFile(file) {
    if (!file || !/\.(ttml|xml|txt)$/i.test(file.name)) {
      setStatus("Выберите файл TTML, XML или TXT.", "error");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setStatus("Текстовый файл слишком большой.", "error");
      return;
    }

    const version = ++textLoadVersion;
    const reader = new FileReader();
    reader.onload = () => {
      if (version !== textLoadVersion) return;
      try {
        if (/\.txt$/i.test(file.name)) {
          plainMode = true;
          plainText.value = String(reader.result || "");
          applyPlainText();
          if (!lines.length) throw new Error("В файле нет текста.");
          ttmlName.textContent = `${file.name} · ${lines.length} строк`;
          ttmlZone.classList.add("is-loaded");
          return;
        }
        const parsed = parseTtml(String(reader.result || ""));
        if (!parsed.length) throw new Error("В TTML нет строк с таймингами.");
        plainMode = false;
        plainText.value = "";
        lines = parsed;
        ttmlName.textContent = `${file.name} · ${lines.length} строк`;
        ttmlZone.classList.add("is-loaded");
        currentLineIndex = null;
        updateReadyState();
      } catch (error) {
        lines = [];
        ttmlZone.classList.remove("is-loaded");
        setStatus(error.message || "Ошибка чтения TTML.", "error");
        updateReadyState();
      }
    };
    reader.onerror = () => setStatus("Не удалось прочитать TTML.", "error");
    reader.readAsText(file, "utf-8");
  }

  function bindDropZone(zone, onFile) {
    ["dragenter", "dragover"].forEach((eventName) => {
      zone.addEventListener(eventName, (event) => {
        event.preventDefault();
        zone.classList.add("is-dragging");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      zone.addEventListener(eventName, (event) => {
        event.preventDefault();
        zone.classList.remove("is-dragging");
      });
    });
    zone.addEventListener("drop", (event) => {
      const file = event.dataTransfer?.files?.[0];
      if (file) onFile(file);
    });
  }

  function formatTime(seconds) {
    if (!Number.isFinite(seconds)) return "0:00";
    const minutes = Math.floor(seconds / 60);
    return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
  }

  function findCandidateIndex(time) {
    let low = 0;
    let high = lines.length - 1;
    let answer = -1;
    while (low <= high) {
      const middle = (low + high) >> 1;
      if (lines[middle].begin <= time) {
        answer = middle;
        low = middle + 1;
      } else {
        high = middle - 1;
      }
    }
    return answer;
  }

  function renderWords(line) {
    currentLine.replaceChildren();
    currentLine.setAttribute("aria-label", line.text);
    line.words.forEach((word) => {
      const element = document.createElement("span");
      element.className = "tp-word";
      element.textContent = word.text;
      currentLine.appendChild(element);
    });
  }

  function renderPosition(time, force = false) {
    const candidate = findCandidateIndex(time);
    const activeIndex = candidate >= 0 && time <= lines[candidate].end ? candidate : -1;
    if (force || activeIndex !== currentLineIndex) {
      currentLineIndex = activeIndex;
      if (activeIndex >= 0) {
        previousLine.textContent = lines[activeIndex - 1]?.text || "";
        nextLine.textContent = lines[activeIndex + 1]?.text || "";
        renderWords(lines[activeIndex]);
      } else {
        previousLine.textContent = candidate >= 0 ? lines[candidate].text : "";
        nextLine.textContent = lines[candidate + 1]?.text || "";
        currentLine.replaceChildren();
        currentLine.removeAttribute("aria-label");
      }
    }

    if (activeIndex >= 0) {
      currentLine.querySelectorAll(".tp-word").forEach((element, wordIndex) => {
        const word = lines[activeIndex].words[wordIndex];
        element.className = "tp-word";
        if (time >= word.end) element.classList.add("is-sung");
        else if (time >= word.begin) element.classList.add("is-active");
      });
    }
  }

  function tick() {
    const offset = Number(offsetRange.value) || 0;
    renderPosition(audio.currentTime + offset);
    if (Number.isFinite(audio.duration) && audio.duration > 0) {
      seek.value = String((audio.currentTime / audio.duration) * 1000);
      timeLabel.textContent = `${formatTime(audio.currentTime)} / ${formatTime(audio.duration)}`;
    }
    if (!audio.paused) animationFrame = requestAnimationFrame(tick);
  }

  function stopAnimation() {
    if (animationFrame !== null) cancelAnimationFrame(animationFrame);
    animationFrame = null;
  }

  function showControls() {
    if (hideTimer !== null) clearTimeout(hideTimer);
    hideTimer = null;
    stage.classList.remove("controls-hidden");
  }

  function scheduleControlsHide() {
    showControls();
    hideTimer = window.setTimeout(() => {
      if (!audio.paused) stage.classList.add("controls-hidden");
    }, 3200);
  }

  function openTool() {
    tool.classList.remove("hidden");
    document.body.classList.add("teleprompter-open");
    byId("tpCloseBtn").focus();
  }

  function closeTool() {
    cancelExport();
    audio.pause();
    stopAnimation();
    showControls();
    tool.classList.add("hidden");
    document.body.classList.remove("teleprompter-open");
    if (document.fullscreenElement && tool.contains(document.fullscreenElement)) {
      document.exitFullscreen().catch(() => {});
    }
    openButton.focus();
  }

  function showSetup() {
    cancelExport();
    audio.pause();
    stopAnimation();
    stage.classList.add("hidden");
    setup.classList.remove("hidden");
    showControls();
  }

  function showStage() {
    if (startButton.disabled) return;
    updateTrackMetadata();
    exportPanel.classList.add("hidden");
    setup.classList.add("hidden");
    stage.classList.remove("hidden");
    currentLineIndex = null;
    previousLine.textContent = "";
    nextLine.textContent = lines[0]?.text || "";
    currentLine.innerHTML = '<span class="tp-placeholder">Готово к воспроизведению</span>';
    renderPosition(audio.currentTime + (Number(offsetRange.value) || 0), true);
  }

  openButton.addEventListener("click", openTool);
  byId("tpCloseBtn").addEventListener("click", closeTool);
  byId("tpExitBtn").addEventListener("click", closeTool);
  byId("tpBackBtn").addEventListener("click", showSetup);
  startButton.addEventListener("click", showStage);

  artistInput.addEventListener("input", updateTrackMetadata);
  titleInput.addEventListener("input", updateTrackMetadata);
  coverInput.addEventListener("change", () => loadCoverFile(coverInput.files?.[0]));
  bindDropZone(coverZone, loadCoverFile);
  byId("tpClearCoverBtn").addEventListener("click", clearCover);
  downloadButton.addEventListener("click", downloadVideo);
  exportCancelButton.addEventListener("click", cancelExport);

  audioInput.addEventListener("change", () => loadAudioFile(audioInput.files?.[0]));
  plainText.addEventListener("input", () => {
    textLoadVersion++;
    plainMode = true;
    ttmlInput.value = "";
    ttmlName.textContent = "Выбрать файл";
    ttmlZone.classList.remove("is-loaded");
    applyPlainText();
  });
  ttmlInput.addEventListener("change", () => loadTtmlFile(ttmlInput.files?.[0]));
  bindDropZone(audioZone, loadAudioFile);
  bindDropZone(ttmlZone, loadTtmlFile);

  playButton.addEventListener("click", () => {
    if (audio.paused) audio.play().catch(() => setStatus("Не удалось воспроизвести аудио.", "error"));
    else audio.pause();
  });
  audio.addEventListener("play", () => {
    playButton.textContent = "Ⅱ";
    playButton.setAttribute("aria-label", "Пауза");
    stopAnimation();
    tick();
    scheduleControlsHide();
  });
  audio.addEventListener("pause", () => {
    playButton.textContent = "▶";
    playButton.setAttribute("aria-label", "Воспроизвести");
    stopAnimation();
    showControls();
    tick();
  });
  audio.addEventListener("ended", () => {
    playButton.textContent = "▶";
    showControls();
  });
  audio.addEventListener("loadedmetadata", () => {
    audioReady = true;
    if (plainMode) applyPlainText();
    else updateReadyState();
    timeLabel.textContent = `0:00 / ${formatTime(audio.duration)}`;
  });
  audio.addEventListener("error", () => {
    audioReady = false;
    startButton.disabled = true;
    setStatus("Браузер не смог прочитать аудиофайл.", "error");
  });

  seek.addEventListener("input", () => {
    if (!Number.isFinite(audio.duration)) return;
    audio.currentTime = (Number(seek.value) / 1000) * audio.duration;
    tick();
  });
  offsetRange.addEventListener("input", () => {
    offsetValue.textContent = `${Number(offsetRange.value).toFixed(1)} с`;
    tick();
  });
  fontScale.addEventListener("input", () => {
    tool.style.setProperty("--tp-scale", fontScale.value);
  });
  mirrorButton.addEventListener("click", () => {
    const active = lyricsWrap.classList.toggle("is-mirrored");
    mirrorButton.setAttribute("aria-pressed", String(active));
  });
  fullscreenButton.addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else tool.requestFullscreen().catch(() => {});
  });
  byId("tpHideBtn").addEventListener("click", () => stage.classList.toggle("controls-hidden"));
  stage.addEventListener("pointermove", () => {
    if (!audio.paused) scheduleControlsHide();
    else showControls();
  });
  stage.addEventListener("pointerdown", () => {
    if (stage.classList.contains("controls-hidden")) showControls();
  });

  document.addEventListener("keydown", (event) => {
    if (tool.classList.contains("hidden")) return;
    if (event.key === "Escape" && !document.fullscreenElement) {
      closeTool();
      return;
    }
    if (exportController || stage.classList.contains("hidden") || event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
    if (event.code === "Space") {
      event.preventDefault();
      playButton.click();
    } else if (event.code === "ArrowRight") {
      audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 5);
      tick();
    } else if (event.code === "ArrowLeft") {
      audio.currentTime = Math.max(0, audio.currentTime - 5);
      tick();
    } else if (event.key.toLowerCase() === "m") {
      mirrorButton.click();
    } else if (event.key.toLowerCase() === "f") {
      fullscreenButton.click();
    }
  });

  window.addEventListener("pagehide", () => {
    cancelExport();
    if (coverUrl) URL.revokeObjectURL(coverUrl);
    if (exportUrl) URL.revokeObjectURL(exportUrl);
    if (audioUrl) URL.revokeObjectURL(audioUrl);
  });
})();
