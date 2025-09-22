const API_BASE = "/api";

const uploadForm = document.getElementById("upload-form");
const uploadStatus = document.getElementById("upload-status");
const voiceSelect = document.getElementById("voice-select");
const chapterStartInput = document.getElementById("chapter-start");
const chapterEndInput = document.getElementById("chapter-end");
const fullBookCheckbox = document.getElementById("full-book-checkbox");
const bookList = document.getElementById("book-list");
const chapterHeading = document.getElementById("chapter-heading");
const chapterAudio = document.getElementById("chapter-audio");
const chapterTextContainer = document.getElementById("chapter-text");
const playButton = document.getElementById("btn-play");
const pauseButton = document.getElementById("btn-pause");
const backButton = document.getElementById("btn-back");
const forwardButton = document.getElementById("btn-forward");
const speedSlider = document.getElementById("speed-slider");
const speedValue = document.getElementById("speed-value");
const alignerSelect = document.getElementById("aligner-select");
const assetLabels = {
    m4b: "Download M4B",
    epub: "Download EPUB",
};

const bookTemplate = document.getElementById("book-item-template");
const chapterTemplate = document.getElementById("chapter-item-template");
const continueTemplate = document.getElementById("continue-card-template");
const featuredTemplate = document.getElementById("featured-card-template");

const viewSections = Array.from(document.querySelectorAll(".view"));
const viewTriggers = Array.from(document.querySelectorAll("[data-view-target]"));
const navTabs = Array.from(document.querySelectorAll(".nav-button"));
const continueList = document.getElementById("continue-list");
const featuredList = document.getElementById("featured-list");
const homeGreeting = document.getElementById("home-greeting");
const homeSeeAllButton = document.getElementById("home-see-all");
const refreshLibraryButton = document.getElementById("refresh-library");

const sampleContinueListening = [
    {
        title: "Twenty Thousand Leagues",
        author: "Jules Verne",
        progress: 0.72,
        durationLabel: "12m left",
    },
    {
        title: "Pride and Prejudice",
        author: "Jane Austen",
        progress: 0.38,
        durationLabel: "25m left",
    },
];

const sampleLibrary = [
    {
        book_id: "the-odyssey",
        book_title: "The Odyssey",
        book_author: "Homer",
        chapters: [
            { index: 1, title: "Book I", status: "preview" },
            { index: 2, title: "Book II", status: "preview" },
        ],
    },
    {
        book_id: "moby-dick",
        book_title: "Moby-Dick",
        book_author: "Herman Melville",
        chapters: [
            { index: 1, title: "Loomings", status: "preview" },
            { index: 2, title: "The Carpet-Bag", status: "preview" },
        ],
    },
    {
        book_id: "sherlock-holmes",
        book_title: "Sherlock Holmes",
        book_author: "Arthur Conan Doyle",
        chapters: [
            { index: 1, title: "A Scandal in Bohemia", status: "preview" },
        ],
    },
];

let libraryLoaded = false;
let libraryCache = [];

let activeChapterButton = null;
let wordSpans = [];
let wordTimings = [];
let currentWordIndex = 0;
let activeSpan = null;
let currentBookId = null;
let currentChapterIndex = null;
let highlightAnimationFrame = null;

function updateGreeting() {
    if (!homeGreeting) {
        return;
    }
    const hour = new Date().getHours();
    let greeting = "Good evening";
    if (hour < 12) {
        greeting = "Good morning";
    } else if (hour < 18) {
        greeting = "Good afternoon";
    }
    homeGreeting.textContent = greeting;
}

function setActiveView(target) {
    viewSections.forEach((section) => {
        section.classList.toggle("active", section.dataset.view === target);
    });
    navTabs.forEach((tab) => {
        tab.classList.toggle("active", tab.dataset.viewTarget === target);
    });
    if (target === "library" && !libraryLoaded) {
        loadBooks({ force: true }).catch(() => {
            renderBooks(sampleLibrary, { fallback: true });
            renderFeatured(sampleLibrary);
        });
    }
}

function renderContinueListening(items) {
    if (!continueList || !continueTemplate) {
        return;
    }
    continueList.innerHTML = "";
    items.forEach((item) => {
        const fragment = continueTemplate.content.cloneNode(true);
        fragment.querySelector('[data-field="title"]').textContent = item.title;
        fragment.querySelector('[data-field="author"]').textContent = item.author;
        const progressLabel = fragment.querySelector('[data-field="progress"]');
        progressLabel.textContent = `${Math.round(item.progress * 100)}% complete`;
        fragment.querySelector('[data-field="duration"]').textContent = item.durationLabel;
        continueList.appendChild(fragment);
    });
}

function renderFeatured(books) {
    if (!featuredList || !featuredTemplate) {
        return;
    }
    featuredList.innerHTML = "";
    const source = books && books.length ? books : sampleLibrary;
    source.slice(0, 6).forEach((book) => {
        const fragment = featuredTemplate.content.cloneNode(true);
        const titleField = fragment.querySelector('[data-field="title"]');
        const authorField = fragment.querySelector('[data-field="author"]');
        titleField.textContent = book.book_title || book.title || book.book_id;
        authorField.textContent = book.book_author || book.author || "";
        featuredList.appendChild(fragment);
    });
}

viewTriggers.forEach((trigger) => {
    trigger.addEventListener("click", () => {
        const target = trigger.dataset.viewTarget;
        if (target) {
            setActiveView(target);
        }
    });
});

if (homeSeeAllButton) {
    homeSeeAllButton.addEventListener("click", () => setActiveView("library"));
}

if (refreshLibraryButton) {
    refreshLibraryButton.addEventListener("click", () => {
        loadBooks({ force: true }).catch(() => {
            renderBooks(sampleLibrary, { fallback: true });
            renderFeatured(sampleLibrary);
        });
    });
}

function resetChapterView() {
    chapterHeading.textContent = "Chapter";
    chapterAudio.pause();
    stopHighlightLoop();
    chapterAudio.src = "";
    chapterTextContainer.textContent = "";
    wordSpans = [];
    wordTimings = [];
    currentWordIndex = 0;
    activeSpan = null;
    activeChapterButton = null;
    currentBookId = null;
    currentChapterIndex = null;
}

function applyChapterRangeDefaults() {
    if (fullBookCheckbox.checked) {
        chapterStartInput.value = 1;
        chapterEndInput.value = -1;
        chapterStartInput.readOnly = true;
        chapterEndInput.readOnly = true;
    } else {
        if (Number(chapterStartInput.value) < 1) {
            chapterStartInput.value = 1;
        }
        if (Number(chapterEndInput.value) < Number(chapterStartInput.value)) {
            chapterEndInput.value = chapterStartInput.value;
        }
        chapterStartInput.readOnly = false;
        chapterEndInput.readOnly = false;
    }
}

fullBookCheckbox.addEventListener("change", applyChapterRangeDefaults);
chapterStartInput.addEventListener("change", () => {
    if (!fullBookCheckbox.checked) {
        if (Number(chapterStartInput.value) < 1) {
            chapterStartInput.value = 1;
        }
        if (Number(chapterEndInput.value) < Number(chapterStartInput.value)) {
            chapterEndInput.value = chapterStartInput.value;
        }
    } else {
        applyChapterRangeDefaults();
    }
});
chapterEndInput.addEventListener("change", () => {
    if (!fullBookCheckbox.checked) {
        if (Number(chapterEndInput.value) < Number(chapterStartInput.value)) {
            chapterEndInput.value = chapterStartInput.value;
        }
    }
});

applyChapterRangeDefaults();

async function fetchJSON(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Request failed with status ${response.status}`);
    }
    return response.json();
}

async function loadVoices() {
    try {
        const data = await fetchJSON(`${API_BASE}/voices/kokoro`);
        voiceSelect.innerHTML = "";
        data.voices.forEach((voice) => {
            const option = document.createElement("option");
            option.value = voice;
            option.textContent = voice;
            voiceSelect.appendChild(option);
        });
    } catch (error) {
        console.error("Failed to load voices", error);
        const fallback = ["af_heart"];
        fallback.forEach((voice) => {
            const option = document.createElement("option");
            option.value = voice;
            option.textContent = voice;
            voiceSelect.appendChild(option);
        });
    }
}

async function loadAligners() {
    if (!alignerSelect) {
        return;
    }

    const defaults = [
        { value: "whisperx", label: "WhisperX" },
        { value: "nemo", label: "NVIDIA NeMo Forced Aligner" },
        { value: "torchaudio", label: "torchaudio CTC Forced Aligner" },
    ];

    try {
        const data = await fetchJSON(`${API_BASE}/aligners`);
        const aligners = Array.isArray(data?.aligners) && data.aligners.length ? data.aligners : defaults.map((entry) => entry.value);
        alignerSelect.innerHTML = "";
        aligners.forEach((name) => {
            const normalized = String(name).toLowerCase();
            const display = defaults.find((entry) => entry.value === normalized)?.label || name;
            const option = document.createElement("option");
            option.value = normalized;
            option.textContent = display;
            alignerSelect.appendChild(option);
        });
    } catch (error) {
        console.warn("Failed to load aligners; using defaults", error);
        alignerSelect.innerHTML = "";
        defaults.forEach((entry) => {
            const option = document.createElement("option");
            option.value = entry.value;
            option.textContent = entry.label;
            alignerSelect.appendChild(option);
        });
    }
}

async function loadBooks({ force = false } = {}) {
    if (!force && libraryLoaded && libraryCache.length) {
        renderBooks(libraryCache);
        renderFeatured(libraryCache);
        return libraryCache;
    }

    try {
        const books = await fetchJSON(`${API_BASE}/books`);
        libraryCache = books;
        libraryLoaded = true;
        renderBooks(books);
        renderFeatured(books);
        return books;
    } catch (error) {
        console.error("Failed to load books", error);
        libraryLoaded = true;
        if (!libraryCache.length) {
            renderBooks(sampleLibrary, { fallback: true });
            renderFeatured(sampleLibrary);
        }
        return [];
    }
}

function renderBooks(books, { fallback = false } = {}) {
    bookList.innerHTML = "";

    if (fallback) {
        const notice = document.createElement("li");
        notice.className = "list-notice";
        notice.textContent = "Showing sample titles while your library is empty.";
        bookList.appendChild(notice);
    }

    if (!books.length) {
        const emptyState = document.createElement("li");
        emptyState.className = "list-notice";
        emptyState.textContent = "No audiobooks generated yet.";
        bookList.appendChild(emptyState);
        return;
    }

    const sorted = [...books].sort((a, b) => (b.generated_ms || 0) - (a.generated_ms || 0));

    sorted.forEach((book) => {
        const fragment = bookTemplate.content.cloneNode(true);
        const listItem = fragment.querySelector("li.list-item");
        const titleField = fragment.querySelector('[data-field="title"]');
        const authorField = fragment.querySelector('[data-field="author"]');
        const chapterContainer = fragment.querySelector('[data-field="chapters"]');
        const deleteButton = fragment.querySelector('[data-field="delete"]');
        const assetsContainer = fragment.querySelector('[data-field="assets"]');

        const bookId = book.book_id || book.id;

        listItem.dataset.bookId = bookId;
        titleField.textContent = book.book_title || book.title || bookId;
        authorField.textContent = book.book_author || book.author || "";

        deleteButton.disabled = fallback;
        deleteButton.title = fallback ? "Sample book" : "Delete";
        if (!fallback) {
            deleteButton.addEventListener("click", () => deleteBookEntry(bookId));
        }

        if (assetsContainer) {
            assetsContainer.innerHTML = "";
            const assetEntries = !fallback && book.assets ? Object.entries(book.assets) : [];
            if (assetEntries.length) {
                assetsContainer.classList.remove("hidden");
                assetEntries.forEach(([kind, filename]) => {
                    if (!filename) {
                        return;
                    }
                    const link = document.createElement("a");
                    link.className = "asset-link";
                    link.textContent = assetLabels[kind] || `Download ${kind}`;
                    link.href = `${API_BASE}/books/${bookId}/assets/${encodeURIComponent(filename)}`;
                    link.setAttribute("download", filename);
                    link.rel = "noopener";
                    assetsContainer.appendChild(link);
                });
            } else {
                assetsContainer.classList.add("hidden");
            }
        }

        (book.chapters || []).forEach((chapter) => {
            const chapterFragment = chapterTemplate.content.cloneNode(true);
            const chapterItem = chapterFragment.querySelector("li.chapter-item");
            const chapterButton = chapterFragment.querySelector("button");
            chapterItem.dataset.chapterIndex = chapter.index;
            chapterButton.textContent = `${chapter.index}. ${chapter.title}`;
            const playable = !fallback && chapter.status === "ready";
            chapterButton.disabled = !playable;
            if (playable) {
                chapterButton.addEventListener("click", () => {
                    loadChapter(bookId, chapter.index, chapterButton);
                });
            }
            chapterContainer.appendChild(chapterFragment);
        });

        bookList.appendChild(fragment);
    });

    if (!fallback) {
        libraryCache = books;
    }
}

async function loadChapter(bookId, chapterIndex, triggerButton) {
    try {
        chapterHeading.textContent = `Chapter ${chapterIndex}`;
        chapterTextContainer.textContent = "Loading chapter...";
        stopHighlightLoop();
        if (activeChapterButton) {
            activeChapterButton.classList.remove("active");
        }
        if (triggerButton) {
            activeChapterButton = triggerButton;
            activeChapterButton.classList.add("active");
        }

        const metadata = await fetchJSON(`${API_BASE}/books/${bookId}/chapters/${chapterIndex}/metadata`);
        currentBookId = bookId;
        currentChapterIndex = chapterIndex;

        renderChapterText(metadata);
        chapterHeading.textContent = `${metadata.chapter_index}. ${metadata.chapter_title}`;

        const audioUrl = `${API_BASE}/books/${bookId}/chapters/${chapterIndex}/audio?cache=${Date.now()}`;
        chapterAudio.src = audioUrl;
        chapterAudio.playbackRate = Number(speedSlider.value);
        chapterAudio.currentTime = 0;
        chapterAudio.pause();
    } catch (error) {
        console.error("Failed to load chapter", error);
        chapterTextContainer.textContent = "Failed to load chapter.";
    }
}

function renderChapterText(metadata) {
    chapterTextContainer.innerHTML = "";
    wordSpans = [];
    wordTimings = [];
    currentWordIndex = 0;
    activeSpan = null;

    const text = metadata.text || "";
    const words = metadata.words || [];
    let cursor = 0;

    words.forEach((word, index) => {
        const segmentText = text.slice(word.char_start, word.char_end);
        if (word.char_start > cursor) {
            chapterTextContainer.appendChild(document.createTextNode(text.slice(cursor, word.char_start)));
        }
        const span = document.createElement("span");
        span.classList.add("token");
        span.dataset.start = word.start_ms;
        span.dataset.end = word.end_ms;
        span.textContent = segmentText;
        chapterTextContainer.appendChild(span);
        wordSpans.push(span);
        wordTimings.push({
            start: Number(word.start_ms),
            end: Number(word.end_ms),
            index,
        });
        cursor = word.char_end;
    });

    if (cursor < text.length) {
        chapterTextContainer.appendChild(document.createTextNode(text.slice(cursor)));
    }
}

function highlightWord(index) {
    if (activeSpan) {
        activeSpan.classList.remove("active");
    }
    if (index >= 0 && index < wordSpans.length) {
        activeSpan = wordSpans[index];
        activeSpan.classList.add("active");
        const rect = activeSpan.getBoundingClientRect();
        const containerRect = chapterTextContainer.getBoundingClientRect();
        if (rect.top < containerRect.top || rect.bottom > containerRect.bottom) {
            activeSpan.scrollIntoView({ block: "center", behavior: "smooth" });
        }
        currentWordIndex = index;
    } else {
        activeSpan = null;
    }
}

function updateHighlight(timeMs) {
    if (!wordTimings.length) {
        return;
    }

    if (currentWordIndex < 0 || currentWordIndex >= wordTimings.length) {
        currentWordIndex = 0;
    }

    if (
        timeMs < wordTimings[currentWordIndex].start
    ) {
        currentWordIndex = 0;
    }

    while (
        currentWordIndex > 0 &&
        timeMs < wordTimings[currentWordIndex].start
    ) {
        currentWordIndex -= 1;
    }

    while (
        currentWordIndex < wordTimings.length - 1 &&
        timeMs > wordTimings[currentWordIndex].end
    ) {
        currentWordIndex += 1;
    }

    const current = wordTimings[currentWordIndex];
    if (timeMs >= current.start && timeMs <= current.end) {
        if (activeSpan !== wordSpans[currentWordIndex]) {
            highlightWord(currentWordIndex);
        }
    } else if (timeMs > current.end && currentWordIndex === wordTimings.length - 1) {
        highlightWord(-1);
    }
}

function runHighlightLoop() {
    updateHighlight(chapterAudio.currentTime * 1000);
    highlightAnimationFrame = requestAnimationFrame(runHighlightLoop);
}

function startHighlightLoop() {
    if (highlightAnimationFrame !== null) {
        return;
    }
    highlightAnimationFrame = requestAnimationFrame(runHighlightLoop);
}

function stopHighlightLoop() {
    if (highlightAnimationFrame !== null) {
        cancelAnimationFrame(highlightAnimationFrame);
        highlightAnimationFrame = null;
    }
}

async function pollTask(taskId) {
    const DELAY = 3000;
    // eslint-disable-next-line no-constant-condition
    while (true) {
        const status = await fetchJSON(`${API_BASE}/tasks/${taskId}`);
        if (status.status === "completed" || status.status === "failed") {
            return status;
        }
        uploadStatus.textContent = `${status.status}...`;
        // eslint-disable-next-line no-await-in-loop
        await new Promise((resolve) => setTimeout(resolve, DELAY));
    }
}

async function deleteBookEntry(bookId) {
    const confirmed = window.confirm("Delete this audiobook? This will remove all generated files.");
    if (!confirmed) {
        return;
    }

    try {
        await fetchJSON(`${API_BASE}/books/${bookId}`, { method: "DELETE" });
        if (currentBookId === bookId) {
            resetChapterView();
        }
        uploadStatus.textContent = "Book deleted.";
        await loadBooks({ force: true });
    } catch (error) {
        console.error("Failed to delete book", error);
        uploadStatus.textContent = error.message;
    }
}

uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const fileInput = document.getElementById("epub-input");
    if (!fileInput.files.length) {
        return;
    }

    const formData = new FormData(uploadForm);
    uploadStatus.textContent = "Uploading...";

    try {
        const response = await fetchJSON(`${API_BASE}/audiobooks`, {
            method: "POST",
            body: formData,
        });
        uploadStatus.textContent = "Processing...";
        const result = await pollTask(response.job_id);
        if (result.status === "completed") {
            uploadStatus.textContent = "Conversion finished.";
            await loadBooks({ force: true });
        } else {
            uploadStatus.textContent = result.detail || "Conversion failed.";
        }
    } catch (error) {
        console.error("Upload failed", error);
        uploadStatus.textContent = error.message;
    }
});

playButton.addEventListener("click", () => chapterAudio.play());
pauseButton.addEventListener("click", () => chapterAudio.pause());
backButton.addEventListener("click", () => {
    chapterAudio.currentTime = Math.max(0, chapterAudio.currentTime - 10);
});
forwardButton.addEventListener("click", () => {
    const target = chapterAudio.currentTime + 10;
    const limit = Number.isFinite(chapterAudio.duration) ? chapterAudio.duration : target;
    chapterAudio.currentTime = Math.min(target, limit);
});
speedSlider.addEventListener("input", (event) => {
    const rate = Number(event.target.value);
    chapterAudio.playbackRate = rate;
    speedValue.textContent = `${rate.toFixed(1)}x`;
});

chapterAudio.addEventListener("timeupdate", () => {
    const currentMs = chapterAudio.currentTime * 1000;
    updateHighlight(currentMs);
});

chapterAudio.addEventListener("seeking", () => {
    const currentMs = chapterAudio.currentTime * 1000;
    currentWordIndex = 0;
    updateHighlight(currentMs);
});

chapterAudio.addEventListener("play", startHighlightLoop);
chapterAudio.addEventListener("pause", stopHighlightLoop);
chapterAudio.addEventListener("ended", () => {
    stopHighlightLoop();
    highlightWord(-1);
});

(async function init() {
    setActiveView("home");
    updateGreeting();
    renderContinueListening(sampleContinueListening);
    renderFeatured(sampleLibrary);

    await loadAligners();
    await loadVoices();
    const books = await loadBooks({ force: true });
    if (books.length) {
        renderFeatured(books);
    }
})();
