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
const downloadAllPdfs = document.querySelector('#download-all-pdfs');
const goldFixInput = document.querySelector('#gold-fix');
const nonGoldMarkupInput = document.querySelector('#non-gold-markup');
const goldMarkupInput = document.querySelector('#gold-markup');
const lastGoldFix = document.querySelector('#last-gold-fix');
const LAST_GOLD_FIX_KEY = 'comireland-last-gold-fix';
let generatedFiles = [];

function enteredNumber(input, fallback) {
  const value = Number(input.value);
  return Number.isFinite(value) && value >= 0 ? value : fallback;
}

function updatePricingRules() {
  const goldFix = enteredNumber(goldFixInput, null);
  const nonGoldMarkup = enteredNumber(nonGoldMarkupInput, 35);
  const goldMarkup = enteredNumber(goldMarkupInput, 27);
  const nonGoldMultiplier = (1 + nonGoldMarkup / 100).toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
  const goldMultiplier = (1 + goldMarkup / 100).toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
  const goldFixText = goldFix === null || goldFix <= 0 ? '[enter Gold Fix]' : `€${goldFix.toFixed(2)}`;
  document.querySelector('#formula-non-gold').textContent = `Non-gold: Supplier Unit Price × ${nonGoldMultiplier} (${nonGoldMarkup}% markup)`;
  document.querySelector('#formula-9ct').textContent = `9CT/9K, Mode t: ${goldFixText} × Metal ÷ Qty + Supplier Unit Price × ${goldMultiplier} (${goldMarkup}% markup)`;
  document.querySelector('#formula-18ct').textContent = `18CT/18K, Mode t: ${goldFixText} × Metal × 2 ÷ Qty + Supplier Unit Price × ${goldMultiplier} (${goldMarkup}% markup)`;
  document.querySelector('#formula-other-gold').textContent = `Gold, another Mode: Supplier Unit Price × ${goldMultiplier} (${goldMarkup}% markup; Metal not included)`;
}

[goldFixInput, nonGoldMarkupInput, goldMarkupInput].forEach(field => field.addEventListener('input', updatePricingRules));
updatePricingRules();

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
  generatedFiles.forEach(file => {
    URL.revokeObjectURL(file.url);
    URL.revokeObjectURL(file.pdfUrl);
  });
  generatedFiles = [];
  fileList.replaceChildren();
  results.classList.add('hidden');
}

function csvBlob(base64) {
  const binary = atob(base64);
  const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
  return new Blob([bytes], { type: 'text/csv;charset=utf-8' });
}

function decodedBlob(base64, type) {
  const binary = atob(base64);
  const bytes = Uint8Array.from(binary, character => character.charCodeAt(0));
  return new Blob([bytes], { type });
}

function triggerDownload(file) {
  const link = Object.assign(document.createElement('a'), { href: file.url, download: file.filename });
  document.body.append(link);
  link.click();
  link.remove();
}

function showResults(data) {
  clearGeneratedFiles();
  generatedFiles = data.files.map(file => ({
    ...file,
    url: URL.createObjectURL(csvBlob(file.content_base64)),
    pdfUrl: URL.createObjectURL(decodedBlob(file.pdf_base64, 'application/pdf')),
  }));
  resultsTitle.textContent = `Invoice #${data.invoice} files`;
  resultsSummary.textContent = `${generatedFiles.length} individual CSV ${generatedFiles.length === 1 ? 'file' : 'files'} created.`;
  generatedFiles.forEach(file => {
    const row = document.createElement('div');
    row.className = 'file-result';
    const details = document.createElement('div');
    details.innerHTML = '<span class="csv-icon">CSV</span><div><strong></strong><small></small></div>';
    details.querySelector('strong').textContent = file.order_ref;
    details.querySelector('small').textContent = `${file.item_count} ${file.item_count === 1 ? 'product' : 'products'} · ${file.filename}`;
    const actions = document.createElement('div');
    actions.className = 'file-actions';
    const link = document.createElement('a');
    link.href = file.url;
    link.download = file.filename;
    link.textContent = 'Download CSV ↓';
    const pdfLink = document.createElement('a');
    pdfLink.href = file.pdfUrl;
    pdfLink.download = file.pdf_filename;
    pdfLink.textContent = 'Download PDF ↓';
    actions.append(link, pdfLink);
    row.append(details, actions);

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
downloadAllPdfs.addEventListener('click', () => generatedFiles.forEach(file => triggerDownload({
  url: file.pdfUrl,
  filename: file.pdf_filename,
})));

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
    updatePricingRules();
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
