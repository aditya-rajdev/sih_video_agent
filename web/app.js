const $ = id => document.getElementById(id);

const topic = $('topic');
const duration = $('duration');
const videoDurationGroup = $('videoDurationGroup');
const tone = $('tone');
const audience = $('audience');
const language = $('language');
const detailLevel = $('detailLevel');
const provider = $('provider');
const apiKey = $('apiKey');
const model = $('model');
const baseUrl = $('baseUrl');
const codeModel = $('codeModel');
const apiGroup = $('apiGroup');
const customGroup = $('customGroup');
const codeModelGroup = $('codeModelGroup');
const generateBtn = $('generateBtn');
const selectAll = $('selectAll');
const outputCards = [...document.querySelectorAll('.output-card[data-output]')];
const statusPanel = $('statusPanel');
const stage = $('stage');
const progressText = $('progressText');
const progressBar = $('progressBar');
const logs = $('logs');
const results = $('results');
const outputResults = $('outputResults');
const scriptReview = $('scriptReview');
const scriptStatus = $('scriptStatus');
const scriptMeta = $('scriptMeta');
const scriptContent = $('scriptContent');
const editBox = $('editBox');
const editInstruction = $('editInstruction');
const videoDecision = $('videoDecision');
const videoResult = $('videoResult');
const video = $('video');
const downloadVideo = $('downloadVideo');
const errorPanel = $('errorPanel');

let currentJobId = null;
let currentVideoJobId = null;
let currentData = null;
let currentScript = null;

function esc(value) {
    const d = document.createElement('div');
    d.textContent = value ?? '';
    return d.innerHTML;
}

function updateProviderUI() {
    const local = provider.value === 'local';
    const custom = provider.value === 'custom';
    apiGroup.classList.toggle('hidden', local);
    customGroup.classList.toggle('hidden', !custom);
    const hasVideo = selectedOutputs().includes('video');
    codeModelGroup.classList.toggle('hidden', !hasVideo);
    videoDurationGroup.classList.toggle('hidden', !hasVideo);
    if (local && !model.value.trim()) model.placeholder = 'Auto: qwen3:8b';
    else if (provider.value === 'groq' && !model.value.trim()) model.placeholder = 'Default: openai/gpt-oss-120b';
    else if (!model.value.trim()) model.placeholder = 'Auto / default model';
}

provider.addEventListener('change', updateProviderUI);

function showError(message) {
    errorPanel.textContent = message;
    errorPanel.classList.remove('hidden');
}
function clearError() {
    errorPanel.classList.add('hidden');
    errorPanel.textContent = '';
}
function setBusy(button, busy, text) {
    button.disabled = busy;
    if (text) button.textContent = text;
}
function selectedOutputs() {
    return outputCards.filter(card => card.classList.contains('selected')).map(card => card.dataset.output);
}
function syncSelectAll() {
    const selected = selectedOutputs().length;
    selectAll.checked = selected === outputCards.length;
    selectAll.indeterminate = selected > 0 && selected < outputCards.length;
    updateProviderUI();
}
outputCards.forEach(card => {
    card.addEventListener('click', () => {
        card.classList.toggle('selected');
        syncSelectAll();
    });
});
selectAll.addEventListener('change', () => {
    outputCards.forEach(card => card.classList.toggle('selected', selectAll.checked));
    syncSelectAll();
});

function resetWorkflowUI() {
    clearError();
    statusPanel.classList.remove('hidden');
    results.classList.add('hidden');
    scriptReview.classList.add('hidden');
    videoDecision.classList.add('hidden');
    videoResult.classList.add('hidden');
    logs.textContent = '';
    progressBar.style.width = '2%';
    progressText.textContent = '2%';
    stage.textContent = 'Starting...';
    outputResults.innerHTML = '';
}

function validateInputs() {
    clearError();
    if (!topic.value.trim()) return 'Please add your source content or prompt.';
    const outputs = selectedOutputs();
    if (!outputs.length) return 'Select at least one output type.';
    if (provider.value !== 'local' && !apiKey.value.trim()) return 'Please enter your API key.';
    if (provider.value === 'custom' && (!model.value.trim() || !baseUrl.value.trim())) return 'Custom API requires model and base URL.';
    return null;
}

function payload() {
    return {
        topic: topic.value.trim(),
        duration: Number(duration.value || 60),
        tone: tone.value,
        audience: audience.value,
        language: language.value,
        detail_level: detailLevel.value,
        provider: provider.value,
        api_key: apiKey.value.trim(),
        model: model.value.trim(),
        base_url: baseUrl.value.trim(),
        code_model: codeModel.value.trim(),
        outputs: selectedOutputs()
    };
}

async function requestJSON(url, options = {}) {
    const response = await fetch(url, {
        headers: {'Content-Type': 'application/json', ...(options.headers || {})},
        ...options
    });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.detail || data.error || 'Request failed.');
    return data;
}

function renderResultCards(data) {
    const selected = data.outputs || [];
    let html = '';

    if (selected.includes('video')) {
        const script = data.script;
        html += `
        <article class="result-card" id="videoOutputCard">
          <div class="result-card-head"><div class="result-title"><span class="output-icon video-icon">▶</span>Video</div><span class="result-status">${script ? 'Script Ready' : 'Pending'}</span></div>
          <div class="result-body">
            <div class="result-preview">${script ? `<b>${esc(script.title)}</b>\n\n${esc(script.hook)}\n\n${script.scenes?.length || 0} scenes · ${script.total_duration}s\n\nVideo rendering waits for script approval.` : 'Video script is being prepared.'}</div>
            <div class="result-actions"><button id="reviewVideoBtn">Review Script</button></div>
          </div>
        </article>`;
    }

    if (selected.includes('linkedin')) {
        const post = data.linkedin || {};
        html += `
        <article class="result-card">
          <div class="result-card-head"><div class="result-title"><span class="output-icon linkedin-icon">in</span>LinkedIn Post</div><span class="result-status">Completed</span></div>
          <div class="result-body"><div class="result-preview"><div class="post-label">POST</div>${esc(post.post || 'No LinkedIn post generated.')}${post.hashtags?.length ? `<div class="post-label hashtags-label">HASHTAGS</div><div>${esc(post.hashtags.map(x => '#' + x.replace(/^#/, '')).join(' '))}</div>` : ''}</div>
          <div class="result-actions"><button data-copy="linkedin">Copy Text</button></div></div>
        </article>`;
    }

    if (selected.includes('x')) {
        const xp = data.x_post || {};
        const posts = xp.posts || [];
        html += `
        <article class="result-card">
          <div class="result-card-head"><div class="result-title"><span class="output-icon x-icon">𝕏</span>Twitter / X Post</div><span class="result-status">Completed</span></div>
          <div class="result-body"><div class="result-preview"><div class="post-label">POST / THREAD</div>${esc(posts.join('\n\n'))}${xp.hashtags?.length ? `<div class="post-label hashtags-label">HASHTAGS</div><div>${esc(xp.hashtags.map(x => '#' + x.replace(/^#/, '')).join(' '))}</div>` : ''}</div>
          <div class="result-actions"><button data-copy="x">Copy ${posts.length > 1 ? 'Thread' : 'Post'}</button></div></div>
        </article>`;
    }

    outputResults.innerHTML = html;
    results.classList.remove('hidden');

    $('reviewVideoBtn')?.addEventListener('click', () => {
        scriptReview.scrollIntoView({behavior:'smooth', block:'start'});
    });
    outputResults.querySelector('[data-copy="linkedin"]')?.addEventListener('click', async e => {
        const post = data.linkedin?.post || '';
        await navigator.clipboard.writeText(post + (data.linkedin?.hashtags?.length ? '\n\n' + data.linkedin.hashtags.map(x=>'#'+x.replace(/^#/,'')).join(' ') : ''));
        e.target.textContent = 'Copied ✓';
    });
    outputResults.querySelector('[data-copy="x"]')?.addEventListener('click', async e => {
        const xp = data.x_post || {};
        const text = [...(xp.posts || []), ...(xp.hashtags?.length ? [xp.hashtags.map(x=>'#'+x.replace(/^#/,'')).join(' ')] : [])].join('\n\n');
        await navigator.clipboard.writeText(text);
        e.target.textContent = 'Copied ✓';
    });
}

function renderScript(script) {
    currentScript = script;
    scriptReview.classList.remove('hidden');
    scriptStatus.textContent = 'DRAFT';
    scriptMeta.innerHTML = `
      <div><b>Title</b><span>${esc(script.title)}</span></div>
      <div><b>Duration</b><span>${Number(script.total_duration) || 0}s</span></div>
      <div><b>Tone</b><span>${esc(script.tone)}</span></div>
      <div><b>Audience</b><span>${esc(script.audience)}</span></div>`;

    let html = `<div class="hook"><b>Hook</b><p>${esc(script.hook)}</p></div>`;
    (script.scenes || []).forEach(scene => {
        const dialogues = (scene.dialogues || []).map(d => `<div class="dialogue"><strong>${esc(d.character)}:</strong> ${esc(d.line)}</div>`).join('');
        html += `<article class="scene-card"><div class="scene-top"><span>Scene ${esc(scene.scene_id)}</span><span>${esc(scene.duration)}s</span></div><div class="scene-body"><div><b>Narration</b><p>${esc(scene.narration)}</p></div>${dialogues ? `<div><b>Dialogue</b>${dialogues}</div>` : ''}<div><b>Visual direction</b><p>${esc(scene.visual_direction)}</p></div>${scene.on_screen_text ? `<div><b>On-screen text</b><p>${esc(scene.on_screen_text)}</p></div>` : ''}</div></article>`;
    });
    if (script.cta) html += `<div class="cta"><b>CTA</b><p>${esc(script.cta)}</p></div>`;
    scriptContent.innerHTML = html;
}

async function generateContent() {
    const error = validateInputs();
    if (error) { showError(error); return; }
    resetWorkflowUI();
    setBusy(generateBtn, true, 'Generating...');

    try {
        const data = await requestJSON('/api/content/generate', {method:'POST', body:JSON.stringify(payload())});
        currentJobId = data.job_id;
        await pollContent(currentJobId);
    } catch (e) {
        showError(e.message);
        setBusy(generateBtn, false, '✦ Generate Selected Content →');
    }
}

async function pollContent(jobId) {
    const data = await requestJSON(`/api/content/${jobId}`);
    currentData = data;
    stage.textContent = data.stage || 'Generating content...';
    progressText.textContent = `${Number(data.progress || 0)}%`;
    progressBar.style.width = `${Number(data.progress || 0)}%`;
    logs.textContent = (data.logs || []).join('\n');
    logs.scrollTop = logs.scrollHeight;

    if (data.status === 'completed') {
        statusPanel.classList.add('hidden');
        renderResultCards(data);
        if (data.script) {
            renderScript(data.script);
        }
        setBusy(generateBtn, false, '✦ Generate Selected Content →');
        return;
    }
    if (data.status === 'failed') throw new Error(data.error || 'Content generation failed.');
    setTimeout(() => pollContent(jobId).catch(e => {showError(e.message); setBusy(generateBtn,false,'✦ Generate Selected Content →');}), 900);
}

$('approveScriptBtn').addEventListener('click', async () => {
    if (!currentJobId) return;
    try {
        setBusy($('approveScriptBtn'), true, 'Approving...');
        const data = await requestJSON(`/api/content/${currentJobId}/script/approve`, {method:'POST'});
        renderScript(data.script);
        scriptStatus.textContent = 'APPROVED';
        videoDecision.classList.remove('hidden');
        videoDecision.scrollIntoView({behavior:'smooth',block:'center'});
    } catch(e) { showError(e.message); }
    finally { setBusy($('approveScriptBtn'), false, '✓ Approve Script'); }
});

$('editScriptBtn').addEventListener('click', () => { editBox.classList.remove('hidden'); editInstruction.focus(); });
$('cancelEditBtn').addEventListener('click', () => editBox.classList.add('hidden'));
$('applyEditBtn').addEventListener('click', async () => {
    if (!currentJobId || !editInstruction.value.trim()) return showError('Enter what you want to change.');
    try {
        setBusy($('applyEditBtn'), true, 'Updating...');
        const data = await requestJSON(`/api/content/${currentJobId}/script/edit`, {method:'POST', body:JSON.stringify({instruction:editInstruction.value.trim()})});
        renderScript(data.script); editInstruction.value=''; editBox.classList.add('hidden');
        if (currentData) { currentData.script = data.script; renderResultCards(currentData); }
    } catch(e) { showError(e.message); }
    finally { setBusy($('applyEditBtn'), false, 'Apply Edit'); }
});

$('regenerateScriptBtn').addEventListener('click', async () => {
    if (!currentJobId) return;
    try {
        setBusy($('regenerateScriptBtn'), true, 'Regenerating...');
        const data = await requestJSON(`/api/content/${currentJobId}/script/regenerate`, {method:'POST'});
        renderScript(data.script);
        if (currentData) { currentData.script = data.script; renderResultCards(currentData); }
    } catch(e) { showError(e.message); }
    finally { setBusy($('regenerateScriptBtn'), false, '↻ Regenerate'); }
});

$('saveScriptBtn').addEventListener('click', async () => {
    if (!currentJobId) return;
    try {
        setBusy($('saveScriptBtn'), true, 'Saving...');
        const data = await requestJSON(`/api/content/${currentJobId}/save-script`, {method:'POST'});
        $('saveScriptBtn').textContent = 'Saved ✓';
        showError(''); errorPanel.classList.add('hidden');
        videoDecision.querySelector('p').textContent = `Script saved to ${data.path}`;
    } catch(e) { showError(e.message); }
    finally { setBusy($('saveScriptBtn'), false, '↓ No, Save Script'); }
});

$('generateVideoBtn').addEventListener('click', async () => {
    if (!currentJobId) return;
    try {
        setBusy($('generateVideoBtn'), true, 'Starting...');
        const data = await requestJSON(`/api/content/${currentJobId}/video`, {method:'POST'});
        currentVideoJobId = data.job_id;
        statusPanel.classList.remove('hidden');
        stage.textContent = 'Starting video pipeline...';
        progressText.textContent = '2%';
        progressBar.style.width = '2%';
        logs.textContent = '';
        await pollVideo(currentVideoJobId);
    } catch(e) { showError(e.message); setBusy($('generateVideoBtn'), false, '▶ Yes, Generate Video'); }
});

async function downloadVideoFile(jobId, button = null) {
    const original = button?.textContent || '⇩ Download MP4';
    try {
        if (button) {
            button.textContent = 'Preparing download...';
            button.style.pointerEvents = 'none';
            button.style.opacity = '0.7';
        }
        const response = await fetch(`/api/video/${jobId}/download`, {
            method: 'GET',
            cache: 'no-store',
        });
        if (!response.ok) {
            let message = 'Video download failed.';
            try {
                const data = await response.json();
                message = data.detail || data.error || message;
            } catch (_) {}
            throw new Error(message);
        }
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = objectUrl;
        anchor.download = 'frameforge-video.mp4';
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
        if (button) button.textContent = 'Downloaded ✓';
    } catch (e) {
        showError(e.message || 'Video download failed.');
    } finally {
        if (button) {
            setTimeout(() => {
                button.textContent = original;
                button.style.pointerEvents = '';
                button.style.opacity = '';
            }, 1500);
        }
    }
}

async function pollVideo(jobId) {
    const data = await requestJSON(`/api/video/${jobId}`);
    stage.textContent = data.stage || 'Rendering video...';
    progressText.textContent = `${Number(data.progress || 0)}%`;
    progressBar.style.width = `${Number(data.progress || 0)}%`;
    logs.textContent = (data.logs || []).join('\n');

    if (data.status === 'completed') {
        const url = `/api/video/${jobId}/file`;
        video.src = `${url}?t=${Date.now()}`;
        downloadVideo.removeAttribute('href');
        downloadVideo.removeAttribute('download');
        downloadVideo.onclick = (event) => {
            event.preventDefault();
            downloadVideoFile(jobId, downloadVideo);
        };
        videoResult.classList.remove('hidden');
        statusPanel.classList.add('hidden');
        videoDecision.classList.add('hidden');
        const card = $('videoOutputCard');
        if (card) {
            const status = card.querySelector('.result-status');
            if (status) status.textContent = 'Video Completed';
            const preview = card.querySelector('.result-preview');
            if (preview) preview.innerHTML = '<b>Final MP4 generated successfully.</b>\n\nThe video was rendered from the approved script using HTML/CSS/JS + Playwright + FFmpeg.';
            const action = card.querySelector('.result-actions');
            if (action) {
                action.innerHTML = '<button class="download" type="button">⇩ Download Video</button>';
                const downloadButton = action.querySelector('.download');
                downloadButton.addEventListener('click', () => downloadVideoFile(jobId, downloadButton));
            }
        }
        setBusy($('generateVideoBtn'), false, '▶ Yes, Generate Video');
        return;
    }
    if (data.status === 'failed') throw new Error(data.error || 'Video generation failed.');
    setTimeout(() => pollVideo(jobId).catch(e => {showError(e.message); setBusy($('generateVideoBtn'),false,'▶ Yes, Generate Video');}), 1200);
}

$('exampleBtn').addEventListener('click', () => {
    topic.value = 'Explain how a solar eclipse happens in simple language for a general audience. Cover the alignment of the Sun, Moon and Earth, total versus partial eclipse, and safe viewing.';
    updateCounter();
});
document.querySelectorAll('.example-chip').forEach(btn => btn.addEventListener('click', () => {topic.value = btn.dataset.example; updateCounter(); topic.focus();}));
function updateCounter(){ $('counter').textContent = `${topic.value.length}/10000`; }
topic.addEventListener('input', updateCounter);

// Add a duration control dynamically if the UI does not expose one yet.
// The current design intentionally keeps duration in the Video output's
// advanced workflow; 60 seconds is the safe default for multi-output runs.

syncSelectAll();
updateProviderUI();
updateCounter();
generateBtn.addEventListener('click', generateContent);
