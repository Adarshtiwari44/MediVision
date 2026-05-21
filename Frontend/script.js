// =============================================================
// State Management
// =============================================================
let selectedFile = null;
let currentReportText = "";
let isChatUnlocked = false;
const BACKEND_URL = "https://medivision-backend-o22d.onrender.com";

let currentLanguage = "en";
let currentAnalysisData = null;
let cachedHindiAnalysis = null;

// =============================================================
// DOM Elements Selection
// =============================================================
const dashboardPage = document.getElementById("dashboardPage");
const uploadZone = document.getElementById("uploadZone");
const fileInput = document.getElementById("fileInput");
const selectedFileInfo = document.getElementById("selectedFileInfo");
const selectedFileName = document.getElementById("selectedFileName");
const btnClearFile = document.getElementById("btnClearFile");
const btnAnalyze = document.getElementById("btnAnalyze");

const loader = document.getElementById("loader");
const welcomeCard = document.getElementById("welcomeCard");
const resultArea = document.getElementById("result");
const reportFilenameBadge = document.getElementById("reportFilenameBadge");

// Card Elements
const analysisSummary = document.getElementById("analysisSummary");
const analysisDiseases = document.getElementById("analysisDiseases");
const analysisDiet = document.getElementById("analysisDiet");
const analysisExercise = document.getElementById("analysisExercise");
const analysisMedicines = document.getElementById("analysisMedicines");
const analysisLifestyle = document.getElementById("analysisLifestyle");

// Collapsible OCR
const ocrChevron = document.getElementById("ocrChevron");
const ocrTextContent = document.getElementById("ocrTextContent");

// Chatbot Elements
const btnChatToggle = document.getElementById("btnChatToggle");
const chatWidget = document.getElementById("chatWidget");
const chatMessages = document.getElementById("chatMessages");
const questionInput = document.getElementById("question");
const btnAsk = document.getElementById("btnAsk");
const systemTimeLabel = document.getElementById("system-time");

// =============================================================
// Canvas Background Animation System
// =============================================================
const canvas = document.getElementById("bg-canvas");
const ctx = canvas.getContext("2d");

let width = window.innerWidth;
let height = window.innerHeight;
canvas.width = width;
canvas.height = height;

// State for floating medical particles
const particles = [];
const particleCount = Math.min(45, Math.floor((width * height) / 35000));

// State for scrolling ECG wave
let ecgOffset = 0;
const ecgSpeed = 1.8; // Calmer speed

class MedicalParticle {
    constructor() {
        this.reset();
        // Distribute randomly initially
        this.x = Math.random() * width;
        this.y = Math.random() * height;
    }

    reset() {
        this.x = Math.random() * width;
        this.y = Math.random() * height;
        this.radius = Math.random() * 2.5 + 1.2;
        this.speedX = (Math.random() - 0.5) * 0.35;
        this.speedY = (Math.random() - 0.5) * 0.35;
        // Mint green, emerald, teal, soft blue-cyan hues
        const hues = [140, 155, 165, 175, 190];
        this.hue = hues[Math.floor(Math.random() * hues.length)];
        this.alpha = Math.random() * 0.22 + 0.08;
        // 30% crosses, 70% circular cells
        this.shape = Math.random() < 0.3 ? "cross" : "circle";
    }

    update() {
        this.x += this.speedX;
        this.y += this.speedY;

        // Wrap around borders
        if (this.x < -10 || this.x > width + 10 || this.y < -10 || this.y > height + 10) {
            this.reset();
            if (Math.random() > 0.5) {
                this.x = Math.random() > 0.5 ? -5 : width + 5;
            } else {
                this.y = Math.random() > 0.5 ? -5 : height + 5;
            }
        }
    }

    draw() {
        ctx.save();
        ctx.fillStyle = `hsla(${this.hue}, 65%, 50%, ${this.alpha})`;
        if (this.shape === "cross") {
            ctx.translate(this.x, this.y);
            const size = this.radius * 1.5;
            const thickness = size / 2.5;
            ctx.fillRect(-size, -thickness / 2, size * 2, thickness);
            ctx.fillRect(-thickness / 2, -size, thickness, size * 2);
        } else {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.restore();
    }
}

// Generate ECG Height baseline offset at coordinate X
function getECGHeight(x, offset) {
    const cycleLength = 320; // Distance between heartbeats
    const phase = (x + offset) % cycleLength;
    
    // Normal sinus rhythm simulation
    if (phase > 200 && phase <= 215) { // P-Wave
        const pPhase = (phase - 200) / 15;
        return Math.sin(pPhase * Math.PI) * -8;
    } else if (phase > 215 && phase <= 222) { // PR Segment
        return 0;
    } else if (phase > 222 && phase <= 226) { // Q-Wave
        const qPhase = (phase - 222) / 4;
        return Math.sin(qPhase * Math.PI) * 5;
    } else if (phase > 226 && phase <= 236) { // QRS Complex (R-Spike)
        const rPhase = (phase - 226) / 10;
        return Math.sin(rPhase * Math.PI) * -65;
    } else if (phase > 236 && phase <= 242) { // S-Wave
        const sPhase = (phase - 236) / 6;
        return Math.sin(sPhase * Math.PI) * 18;
    } else if (phase > 242 && phase <= 255) { // ST Segment
        return 0;
    } else if (phase > 255 && phase <= 280) { // T-Wave
        const tPhase = (phase - 255) / 25;
        return Math.sin(tPhase * Math.PI) * -12;
    }
    return 0;
}

// Initialize particles array
for (let i = 0; i < particleCount; i++) {
    particles.push(new MedicalParticle());
}

// Main background animation render loop
function animate() {
    ctx.clearRect(0, 0, width, height);

    // 1. Draw Subtle Medical Grid
    ctx.strokeStyle = "rgba(16, 185, 129, 0.035)";
    ctx.lineWidth = 1;
    const gridSpacing = 40;
    for (let x = 0; x < width; x += gridSpacing) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
    }
    for (let y = 0; y < height; y += gridSpacing) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
    }

    // 2. Draw Scrolling ECG Lines (2 separate offset layers for depth)
    ecgOffset += ecgSpeed;
    
    // Background faint ECG
    ctx.strokeStyle = "rgba(13, 148, 136, 0.02)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    let centerY2 = height * 0.65;
    for (let x = 0; x < width; x += 3) {
        let y = centerY2 + getECGHeight(x, ecgOffset * 0.7);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Foreground calm ECG
    ctx.strokeStyle = "rgba(16, 185, 129, 0.05)";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    let centerY1 = height * 0.45;
    for (let x = 0; x < width; x += 2) {
        let y = centerY1 + getECGHeight(x, ecgOffset);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // 3. Update & Draw Medical Particles
    for (let i = 0; i < particles.length; i++) {
        const p1 = particles[i];
        p1.update();
        p1.draw();

        // Draw connections to nearby particles (molecular telemetry grid)
        for (let j = i + 1; j < particles.length; j++) {
            const p2 = particles[j];
            const dist = Math.hypot(p1.x - p2.x, p1.y - p2.y);
            if (dist < 110) {
                const connAlpha = (1 - (dist / 110)) * 0.06;
                ctx.strokeStyle = `rgba(16, 185, 129, ${connAlpha})`;
                ctx.lineWidth = 0.8;
                ctx.beginPath();
                ctx.moveTo(p1.x, p1.y);
                ctx.lineTo(p2.x, p2.y);
                ctx.stroke();
            }
        }
    }

    requestAnimationFrame(animate);
}

// Window resize listener
window.addEventListener("resize", () => {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;
});

// Run Background Animations immediately
requestAnimationFrame(animate);

// =============================================================
// Clock System
// =============================================================
function updateSystemTime() {
    if (systemTimeLabel) {
        const now = new Date();
        const timeStr = now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
        systemTimeLabel.textContent = timeStr;
    }
}
setInterval(updateSystemTime, 1000);
updateSystemTime();

function enterApp() {
    const landing = document.getElementById("landingPage");
    const dashboard = document.getElementById("dashboardPage");
    
    landing.classList.add("fade-out-exit");
    
    setTimeout(() => {
        landing.style.display = "none";
        dashboard.classList.remove("hidden");
        dashboard.classList.add("fade-in-entry");
    }, 600);
}
window.enterApp = enterApp;

function returnToLanding() {
    clearSelectedFile();
    resultArea.style.display = "none";
    welcomeCard.style.display = "flex";
    const chatHeaderSpan = document.querySelector("#chatWidget .status-online");
    if (chatHeaderSpan) {
        chatHeaderSpan.innerHTML = `<span class="online-dot"></span> Secure Advisory Stream`;
    }
    
    const landing = document.getElementById("landingPage");
    const dashboard = document.getElementById("dashboardPage");
    
    dashboard.classList.add("hidden");
    dashboard.classList.remove("fade-in-entry");
    landing.style.display = "flex";
    landing.classList.remove("fade-out-exit");
    
    window.scrollTo({ top: 0, behavior: 'smooth' });
}
window.returnToLanding = returnToLanding;

// =============================================================
// File Intake & Drag & Drop Handling
// =============================================================
let activeCategory = "report"; // Default to Clinical Report

function switchTab(category) {
    if (activeCategory === category) return;
    
    activeCategory = category;
    const tabReport = document.getElementById("tabReport");
    const tabXray = document.getElementById("tabXray");
    const uploadText = document.getElementById("uploadPrimaryText");
    const uploadSub = document.getElementById("uploadSecondaryText");
    const btnText = document.getElementById("btnAnalyzeText");
    
    if (category === "report") {
        tabReport.classList.add("active");
        tabXray.classList.remove("active");
        uploadText.textContent = "🩺 Upload Clinical Report";
        uploadSub.textContent = "Drop your PDF, Blood Report, MRI, X-ray, or Prescription here for AI-powered medical analysis.";
        btnText.textContent = "RUN CLINICAL SYNTHESIS";
    } else {
        tabXray.classList.add("active");
        tabReport.classList.remove("active");
        uploadText.textContent = "🩻 Upload Diagnostic Scan";
        uploadSub.textContent = "Drop your Chest X-ray, MRI, Mammogram, or CT scan image here for automated diagnostics.";
        btnText.textContent = "RUN IMAGING DIAGNOSTICS";
    }
    
    // Clear out previous selections to keep inputs clean
    clearSelectedFile();
}

window.switchTab = switchTab;

document.addEventListener("DOMContentLoaded", () => {
    // Connect upload click
    uploadZone.addEventListener("click", () => {
        fileInput.click();
    });

    fileInput.addEventListener("change", handleFileChange);
    btnClearFile.addEventListener("click", (e) => {
        e.stopPropagation();
        clearSelectedFile();
    });

    // Drag-and-drop visual indicators
    ["dragenter", "dragover"].forEach(eventName => {
        uploadZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadZone.classList.add("dragover");
        }, false);
    });

    ["dragleave", "drop"].forEach(eventName => {
        uploadZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            uploadZone.classList.remove("dragover");
        }, false);
    });

    uploadZone.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            const file = files[0];
            const allowed = /\.(pdf|png|jpg|jpeg|avif)$/i;
            if (!allowed.test(file.name)) {
                showUploadError("Unsupported format. Please upload PDF, PNG, JPG, JPEG, or AVIF.");
                return;
            }
            fileInput.files = files;
            handleFileChange();
        }
    });

    // Chatbot keypress submit
    questionInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            askQuestion();
        }
    });

    // Auto-unlock chatbot on load
    unlockChatbot();
});

function handleFileChange() {
    if (fileInput.files && fileInput.files.length > 0) {
        selectedFile = fileInput.files[0];

        // Validate file type (including AVIF)
        const allowed = /\.(pdf|png|jpg|jpeg|avif)$/i;
        if (!allowed.test(selectedFile.name)) {
            showUploadError("Unsupported format. Please upload PDF, PNG, JPG, JPEG, or AVIF.");
            clearSelectedFile();
            return;
        }

        // Show file card (now sits OUTSIDE upload zone — no layout break)
        selectedFileName.textContent = selectedFile.name;
        selectedFileInfo.style.display = "flex";
        // Do NOT hide .upload-zone-content — zone stays centered and intact
        btnAnalyze.disabled = false;

        // Success pulse on the zone border
        uploadZone.classList.add("upload-success");
        setTimeout(() => uploadZone.classList.remove("upload-success"), 1000);
        uploadZone.style.borderColor = "var(--color-primary)";
    } else {
        clearSelectedFile();
    }
}

function showUploadError(msg) {
    // Show a friendly inline error toast instead of alert()
    const existing = document.getElementById("uploadErrorToast");
    if (existing) existing.remove();
    const toast = document.createElement("div");
    toast.id = "uploadErrorToast";
    toast.className = "upload-error-toast";
    toast.textContent = "⚠️ " + msg;
    const zone = document.getElementById("uploadZone");
    zone.parentNode.insertBefore(toast, zone.nextSibling);
    setTimeout(() => toast.remove(), 4000);
}

function clearSelectedFile() {
    selectedFile = null;
    fileInput.value = "";
    selectedFileName.textContent = "No file selected";
    selectedFileInfo.style.display = "none";
    // Upload zone content always stays visible now (card is outside the zone)
    uploadZone.style.borderColor = "rgba(16, 185, 129, 0.25)";
    btnAnalyze.disabled = true;
}

// =============================================================
// Backend Clinical Telemetry Integration
// =============================================================
async function uploadReport() {
    if (!selectedFile) {
        alert("Please feed a clinical file into the scanner intake first.");
        return;
    }

    // Toggle scanning laser sweep animation
    uploadZone.classList.add("processing");
    welcomeCard.style.display = "none";
    resultArea.style.display = "none";
    loader.style.display = "flex";
    
    const loaderText = document.querySelector(".loader-text");
    const loaderSubtext = document.querySelector(".loader-subtext");
    
    const isXray = activeCategory === "xray";
    if (isXray) {
        loaderText.textContent = "RUNNING IMAGING NEURAL SCANNER...";
        loaderSubtext.textContent = "Processing scan matrices using local vision models & querying Gemini AI";
    } else {
        loaderText.textContent = "RUNNING COGNITIVE BIOMARKER ALIGNMENT...";
        loaderSubtext.textContent = "Extracting telemetry values via OCR & querying clinical knowledge base";
    }

    // Lock controls
    btnAnalyze.disabled = true;
    fileInput.disabled = true;
    btnClearFile.disabled = true;

    // Reset results container animate classes
    resultArea.classList.remove("active-results");

    const formData = new FormData();
    formData.append("file", selectedFile);

    const endpoint = isXray ? "/analyze-xray" : "/upload-report";

    try {
        const response = await fetch(`${BACKEND_URL}${endpoint}`, {
            method: "POST",
            body: formData
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Clinical server alignment error.");
        }

        const data = await response.json();
        
        if (data.success) {
            reportFilenameBadge.textContent = data.filename;

            if (isXray) {
                // Compile report text for chatbot context
                currentReportText = `X-Ray Scan Analysis:\nFilename: ${data.filename}\nOverall Detections: ${data.detections.join(", ")}\nAverage Confidence: ${data.confidence}\nSummary: ${data.summary}\nRecommendations:\n- Diet: ${data.diet}\n- Exercise: ${data.exercise}\n- Medicines: ${data.medicines}\n- Lifestyle: ${data.lifestyle}`;

                const detectionsMd = `**Detections:**\n${data.detections.map(d => `- ${d}`).join("\n")}\n\n**Average Confidence:** ${data.confidence}`;

                currentAnalysisData = {
                    summary: data.summary || "",
                    diseases: detectionsMd,
                    diet: data.diet || "",
                    exercise: data.exercise || "",
                    medicines: data.medicines || "",
                    lifestyle: data.lifestyle || ""
                };

                analysisSummary.innerHTML = formatMarkdown(currentAnalysisData.summary);
                analysisDiseases.innerHTML = formatMarkdown(currentAnalysisData.diseases);
                analysisDiet.innerHTML = formatMarkdown(currentAnalysisData.diet);
                analysisExercise.innerHTML = formatMarkdown(currentAnalysisData.exercise);
                analysisMedicines.innerHTML = formatMarkdown(currentAnalysisData.medicines);
                analysisLifestyle.innerHTML = formatMarkdown(currentAnalysisData.lifestyle);

                // Raw telemetry collapsor shows predictions details
                ocrTextContent.textContent = `Overall Detections: ${JSON.stringify(data.detections, null, 2)}\nAverage Confidence: ${data.confidence}\n\nRecommendations payload:\n${data.recommendation}`;
            } else {
                currentReportText = data.extracted_text || "No report text loaded.";

                // Load analysis payload
                const analysis = data.ai_analysis;
                
                currentAnalysisData = {
                    summary: analysis.summary || "",
                    diseases: analysis.diseases || "",
                    diet: analysis.diet || "",
                    exercise: analysis.exercise || "",
                    medicines: analysis.medicines || "",
                    lifestyle: analysis.lifestyle || ""
                };

                analysisSummary.innerHTML = formatMarkdown(currentAnalysisData.summary);
                analysisDiseases.innerHTML = formatMarkdown(currentAnalysisData.diseases);
                analysisDiet.innerHTML = formatMarkdown(currentAnalysisData.diet);
                analysisExercise.innerHTML = formatMarkdown(currentAnalysisData.exercise);
                analysisMedicines.innerHTML = formatMarkdown(currentAnalysisData.medicines);
                analysisLifestyle.innerHTML = formatMarkdown(currentAnalysisData.lifestyle);

                // Raw OCR collapsor
                ocrTextContent.textContent = data.extracted_text || "No parameters decoded via OCR scans.";
            }

            cachedHindiAnalysis = null;
            currentLanguage = "en";
            updateLangToggleButtonUI();

            // Switch loader off & display cards grid
            loader.style.display = "none";
            resultArea.style.display = "flex";
            
            // Trigger card stagger entrance transitions
            setTimeout(() => {
                resultArea.classList.add("active-results");
            }, 50);

            // Notify chatbot of report intake completion
            const chatHeaderSpan = document.querySelector("#chatWidget .status-online");
            if (chatHeaderSpan) {
                chatHeaderSpan.innerHTML = `<span class="online-dot"></span> Consultation Stream: ${data.filename}`;
            }
            
            const messageType = isXray ? "X-ray scan analysis" : "clinical report";
            appendSystemMessage(`🧬 Telemetry updated. Chatbot context aligned with ${messageType}: <strong>${data.filename}</strong>.`);
        } else {
            throw new Error("Unable to synthesize document data.");
        }

    } catch (error) {
        console.error("Clinical Intake Alignment Error:", error);
        loader.style.display = "none";
        welcomeCard.style.display = "flex";
        alert(`Intake Alignment Refused: ${error.message}`);
    } finally {
        uploadZone.classList.remove("processing");
        btnAnalyze.disabled = false;
        fileInput.disabled = false;
        btnClearFile.disabled = false;
    }
}

window.uploadReport = uploadReport;

// =============================================================
// Chatbot Consultant Logic
// =============================================================
function unlockChatbot() {
    if (isChatUnlocked) return;
    
    isChatUnlocked = true;
    
    // Enable floating widget toggle
    btnChatToggle.classList.remove("disabled");
    
    // Enable text inputs
    questionInput.disabled = false;
    btnAsk.disabled = false;
    
    // Initial consult bubble
    const greetingText = currentLanguage === "hi" 
        ? "🩺 Aapka clinical consultation stream me swagat hai. Aap wellness ke bare me koi bhi sawal pooch sakte hain ya medical report upload karke discuss kar sakte hain."
        : "🩺 Welcome to your clinical consultation stream. Ask general wellness queries or upload medical data to initiate deep context consultations.";

    chatMessages.innerHTML = `
        <div class="chat-bubble ai-bubble">
            ${greetingText}
        </div>
    `;
}

function toggleChatWidget() {
    if (!isChatUnlocked) return;
    chatWidget.classList.toggle("chat-widget-closed");
    if (!chatWidget.classList.contains("chat-widget-closed")) {
        setTimeout(() => questionInput.focus(), 150);
    }
}

window.toggleChatWidget = toggleChatWidget;

async function askQuestion() {
    const question = questionInput.value.trim();
    if (!question) return;

    // Output user bubble
    appendMessage(question, "user");
    questionInput.value = "";
    
    // Lock inputs while generating response
    questionInput.disabled = true;
    btnAsk.disabled = true;

    // Render Jarvis typing bubble indicator
    const typingBubble = appendTypingIndicator();

    // Set fallback if no report context exists yet
    const queryContextText = currentReportText || "No report uploaded. Patient is asking general wellness questions.";

    // Hinglish suffix modification for chatbot response style alignment
    let finalQuestion = question;
    if (currentLanguage === "hi") {
        finalQuestion = `[Hinglish Mode] ${question}`;
    }

    try {
        const response = await fetch(`${BACKEND_URL}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                question: finalQuestion,
                report_text: queryContextText
            })
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Neural console timeout.");
        }

        const data = await response.json();
        typingBubble.remove();

        if (data.success) {
            appendMessage(data.answer, "ai");
        } else {
            throw new Error("Unable to parse stream consult.");
        }

    } catch (error) {
        console.error("Consultation stream error:", error);
        typingBubble.remove();
        appendMessage(`⚠️ Connection interrupted: ${error.message}`, "ai system-bubble");
    } finally {
        questionInput.disabled = false;
        btnAsk.disabled = false;
        questionInput.focus();
    }
}

window.askQuestion = askQuestion;

// =============================================================
// Collapsible OCR Text Panel
// =============================================================
function toggleOcrText() {
    const isCollapsed = ocrTextContent.classList.contains("collapsed");
    const ocrCard = document.querySelector(".ocr-card");

    if (isCollapsed) {
        ocrTextContent.classList.remove("collapsed");
        ocrCard.classList.remove("collapsed");
        ocrChevron.style.transform = "rotate(180deg)";
    } else {
        ocrTextContent.classList.add("collapsed");
        ocrCard.classList.add("collapsed");
        ocrChevron.style.transform = "rotate(0deg)";
    }
}

window.toggleOcrText = toggleOcrText;

// =============================================================
// Helper Utilities & Formatting
// =============================================================
function appendMessage(text, sender) {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${sender}-bubble`;
    
    if (sender === "user") {
        bubble.textContent = text;
    } else {
        // AI responses get basic markdown and newline spacing parsed
        bubble.innerHTML = formatMarkdown(text);
    }
    
    chatMessages.appendChild(bubble);
    chatMessages.scrollTo({
        top: chatMessages.scrollHeight,
        behavior: 'smooth'
    });
    return bubble;
}

function appendSystemMessage(text) {
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble ai-bubble system-bubble";
    bubble.innerHTML = text;
    chatMessages.appendChild(bubble);
    chatMessages.scrollTo({
        top: chatMessages.scrollHeight,
        behavior: 'smooth'
    });
}

function appendTypingIndicator() {
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble typing-bubble";
    bubble.innerHTML = `
        <div class="typing-dots">
            <span></span>
            <span></span>
            <span></span>
        </div>
    `;
    chatMessages.appendChild(bubble);
    chatMessages.scrollTo({
        top: chatMessages.scrollHeight,
        behavior: 'smooth'
    });
    return bubble;
}

/**
 * Basic Markdown to HTML Formatter
 * Supports Bold (**text**), Bullet Lists (- or *), and Paragraphs.
 * Keep output compact to improve readability.
 */
function formatMarkdown(text) {
    if (!text) return "";
    
    // Escape standard tags to prevent DOM injection
    let html = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");

    // Restore safe SVG tags and their children / attributes
    html = html.replace(/&lt;(\/?(?:svg|path|circle|rect|line|polyline|ellipse|g|polygon))(\s|&gt;|.*?\/?)&gt;/gi, (match, tag, attrs) => {
        let decodedAttrs = attrs
            .replace(/&amp;/g, "&")
            .replace(/&quot;/g, '"')
            .replace(/&#x27;/g, "'")
            .replace(/&lt;/g, "<")
            .replace(/&gt;/g, ">");
        return `<${tag}${decodedAttrs}>`;
    });

    // Bold tags (**text**)
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

    // Bullet lines split parsing
    const lines = html.split("\n");
    let formattedLines = [];
    let listOpen = false;

    for (let line of lines) {
        let trimmed = line.trim();
        
        // Bullet list tags (- or * or •)
        if (trimmed.startsWith("- ") || trimmed.startsWith("* ") || trimmed.startsWith("• ")) {
            if (!listOpen) {
                formattedLines.push("<ul>");
                listOpen = true;
            }
            const itemContent = trimmed.substring(2).trim();
            formattedLines.push(`<li>${itemContent}</li>`);
        } else {
            if (listOpen) {
                formattedLines.push("</ul>");
                listOpen = false;
            }
            
            if (trimmed) {
                formattedLines.push(`<p>${trimmed}</p>`);
            }
        }
    }

    if (listOpen) {
        formattedLines.push("</ul>");
    }

    return formattedLines.join("\n");
}

// =============================================================
// Language Toggle and Translation Logic
// =============================================================
function updateLangToggleButtonUI() {
    const btn = document.getElementById("btnToggleLang");
    if (!btn) return;
    if (currentLanguage === "hi") {
        btn.classList.add("hindi-active");
    } else {
        btn.classList.remove("hindi-active");
    }
}

function parseJsonSafely(text) {
    if (!text) return null;
    let cleaned = text.trim();
    if (cleaned.startsWith("```")) {
        const lines = cleaned.split("\n");
        if (lines[0].startsWith("```")) {
            cleaned = lines.slice(1).join("\n");
        }
        if (cleaned.endsWith("```")) {
            cleaned = cleaned.substring(0, cleaned.length - 3);
        }
        cleaned = cleaned.trim();
    }
    const firstBrace = cleaned.indexOf('{');
    const lastBrace = cleaned.lastIndexOf('}');
    if (firstBrace !== -1 && lastBrace !== -1 && lastBrace > firstBrace) {
        cleaned = cleaned.substring(firstBrace, lastBrace + 1);
    }
    try {
        return JSON.parse(cleaned);
    } catch (e) {
        console.error("JSON parsing failed in frontend helper:", e);
        return null;
    }
}

async function toggleLanguage() {
    if (!currentAnalysisData) return;

    if (currentLanguage === "en") {
        currentLanguage = "hi";
        updateLangToggleButtonUI();
        
        // If Hindi translation is not cached, fetch it
        if (!cachedHindiAnalysis) {
            setCardsLoadingState();
            
            try {
                const response = await fetch(`${BACKEND_URL}/chat`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        question: "Translate the following medical analysis cards content into simple Hindi. Keep the markdown formatting, emojis, and inline SVGs completely intact. Do not add any conversational text before or after the JSON. Respond ONLY with a valid JSON object matching the keys (summary, diseases, diet, exercise, medicines, lifestyle) as defined in the input: " + JSON.stringify(currentAnalysisData),
                        report_text: "Translation task. Target language: Hindi."
                    })
                });

                if (!response.ok) {
                    throw new Error("Translation request failed.");
                }

                const data = await response.json();
                if (data.success && data.answer) {
                    const parsed = parseJsonSafely(data.answer);
                    if (parsed && parsed.summary) {
                        cachedHindiAnalysis = parsed;
                    } else {
                        console.warn("Direct JSON parsing failed, attempting raw parse fallback");
                        let text = data.answer.trim();
                        if (text.startsWith("```")) {
                            const lines = text.split("\n");
                            text = lines.slice(1, -1).join("\n").trim();
                        }
                        const firstBrace = text.indexOf('{');
                        const lastBrace = text.lastIndexOf('}');
                        if (firstBrace !== -1 && lastBrace !== -1) {
                            text = text.substring(firstBrace, lastBrace + 1);
                        }
                        cachedHindiAnalysis = JSON.parse(text);
                    }
                } else {
                    throw new Error("Invalid response format.");
                }
            } catch (error) {
                console.error("Hindi translation failed:", error);
                currentLanguage = "en";
                updateLangToggleButtonUI();
                alert("Translation failed. Please try again. (अनुवाद विफल रहा)");
                applyAnalysisData(currentAnalysisData);
                return;
            }
        }
        
        // Render Hindi content
        applyAnalysisData(cachedHindiAnalysis);
        appendMessage("🌐 Language switched to Hindi. Chatbot will now respond in Hinglish.", "ai system-bubble");
    } else {
        currentLanguage = "en";
        updateLangToggleButtonUI();
        // Render English content
        applyAnalysisData(currentAnalysisData);
        appendMessage("🌐 Language switched to English.", "ai system-bubble");
    }
}

function setCardsLoadingState() {
    const cards = [analysisSummary, analysisDiseases, analysisDiet, analysisExercise, analysisMedicines, analysisLifestyle];
    cards.forEach(card => {
        card.classList.add("fade-out");
    });
    setTimeout(() => {
        cards.forEach(card => {
            card.innerHTML = `<div class="translation-loader"><span class="loading-dot"></span><span class="loading-dot"></span><span class="loading-dot"></span><br><small style="color:var(--color-primary);font-size:0.8rem;font-weight:600;">Translating / अनुवाद किया जा रहा है...</small></div>`;
            card.classList.remove("fade-out");
        });
    }, 250);
}

function applyAnalysisData(data) {
    const cards = [
        { el: analysisSummary, text: data.summary },
        { el: analysisDiseases, text: data.diseases },
        { el: analysisDiet, text: data.diet },
        { el: analysisExercise, text: data.exercise },
        { el: analysisMedicines, text: data.medicines },
        { el: analysisLifestyle, text: data.lifestyle }
    ];

    cards.forEach(c => {
        c.el.classList.add("fade-out");
    });

    setTimeout(() => {
        cards.forEach(c => {
            c.el.innerHTML = formatMarkdown(c.text || "");
            c.el.classList.remove("fade-out");
        });
    }, 250);
}

window.toggleLanguage = toggleLanguage;

function appendSystemMessage(text) {
    return appendMessage(text, "ai system-bubble");
}
