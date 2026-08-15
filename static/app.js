const form = document.querySelector('#processor');
const input = document.querySelector('#invoice');
const dropzone = document.querySelector('#dropzone');
const fileName = document.querySelector('#file-name');
const button = document.querySelector('#submit');
const message = document.querySelector('#message');
const results = document.querySelector('#results');
const resultsTitle = document.querySelector('#results-title');
const resultsSummary = document.querySelector('#results-summary');
const fileList = document.querySelector('#file-list');
const downloadAll = document.querySelector('#download-all');
const goldFixInput = document.querySelector('#gold-fix');
const lastGoldFix = document.querySelector('#last-gold-fix');
const LAST_GOLD_FIX_KEY = 'comireland-last-gold-fix';
let generatedFiles = [];

function displayLastGoldFix(value) {
  const parsed = Number(value);
  lastGoldFix.textContent = Number.isFinite(parsed) && parsed > 0 ? `€ ${parsed.toFixed(2)}` : 'No previous value';
}

try {
  displayLastGoldFix(localStorage.getItem(LAST_GOLD_FIX_KEY));
} catch {
  displayLastGoldFix(null);
}

function clearGeneratedFiles() {
  generatedFiles.forEach(file => URL.revokeObjectURL(file.url));
  generatedFiles = [];
  fileList.replaceChildren();
  results.classList.add('hidden');
}

function csvBlob(base64) {
  const binary = atob(base64);
  const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
  return new Blob([bytes], { type: 'text/csv;charset=utf-8' });
}

function triggerDownload(file) {
  const link = Object.assign(document.createElement('a'), { href: file.url, download: file.filename });
  document.body.append(link);
  link.click();
  link.remove();
}

function showResults(data) {
  clearGeneratedFiles();
  generatedFiles = data.files.map(file => ({ ...file, url: URL.createObjectURL(csvBlob(file.content_base64)) }));
  resultsTitle.textContent = `Invoice #${data.invoice}`;
  resultsSummary.textContent = `${generatedFiles.length} individual CSV ${generatedFiles.length === 1 ? 'file' : 'files'} created.`;
  generatedFiles.forEach(file => {
    const row = document.createElement('div');
    row.className = 'file-result';
    const details = document.createElement('div');
    details.innerHTML = '<span class="csv-icon">CSV</span><div><strong></strong><small></small></div>';
    details.querySelector('strong').textContent = file.order_ref;
    details.querySelector('small').textContent = `${file.item_count} ${file.item_count === 1 ? 'product' : 'products'} · ${file.filename}`;
    const link = document.createElement('a');
    link.href = file.url;
    link.download = file.filename;
    link.textContent = 'Download CSV ↓';
    row.append(details, link);

    const preview = document.createElement('details');
    preview.className = 'csv-preview';
    preview.innerHTML = '<summary>Preview CSV</summary><div class="preview-scroll"><table><tbody></tbody></table></div>';
    const body = preview.querySelector('tbody');
    file.preview_rows.forEach((values, rowIndex) => {
      const tableRow = document.createElement('tr');
      const columns = Math.max(values.length, 8);
      for (let column = 0; column < columns; column += 1) {
        const cell = document.createElement(rowIndex === 5 ? 'th' : 'td');
        cell.textContent = values[column] ?? '';
        tableRow.append(cell);
      }
      body.append(tableRow);
    });
    const result = document.createElement('article');
    result.className = 'file-card';
    result.append(row, preview);
    fileList.append(result);
  });
  results.classList.remove('hidden');
  results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function showFile() {
  fileName.textContent = input.files[0]?.name || 'Drop an invoice here';
  dropzone.classList.toggle('selected', Boolean(input.files[0]));
}

input.addEventListener('change', showFile);
['dragenter', 'dragover'].forEach(type => dropzone.addEventListener(type, () => dropzone.classList.add('dragging')));
['dragleave', 'drop'].forEach(type => dropzone.addEventListener(type, () => dropzone.classList.remove('dragging')));
downloadAll.addEventListener('click', () => generatedFiles.forEach(triggerDownload));

form.addEventListener('submit', async event => {
  event.preventDefault();
  const usedGoldFix = goldFixInput.value;
  message.className = 'message';
  message.textContent = 'Reading products and preparing your CSV files…';
  button.disabled = true;
  button.classList.add('working');
  try {
    const response = await fetch('/api/process', { method: 'POST', body: new FormData(form) });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || 'Invoice processing failed.');
    }
    showResults(await response.json());
    try {
      localStorage.setItem(LAST_GOLD_FIX_KEY, usedGoldFix);
    } catch {
      // The app still works when browser storage is unavailable.
    }
    displayLastGoldFix(usedGoldFix);
    goldFixInput.value = '';
    message.className = 'message success';
    message.textContent = 'Done — choose individual files below or download them all.';
  } catch (error) {
    message.className = 'message error';
    message.textContent = error.message;
  } finally {
    button.disabled = false;
    button.classList.remove('working');
  }
});
