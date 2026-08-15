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
let generatedFiles = [];

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
    fileList.append(row);
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
