const form = document.querySelector('#processor');
const input = document.querySelector('#invoice');
const dropzone = document.querySelector('#dropzone');
const fileName = document.querySelector('#file-name');
const button = document.querySelector('#submit');
const message = document.querySelector('#message');

function showFile() {
  fileName.textContent = input.files[0]?.name || 'Drop an invoice here';
  dropzone.classList.toggle('selected', Boolean(input.files[0]));
}
input.addEventListener('change', showFile);
['dragenter', 'dragover'].forEach(type => dropzone.addEventListener(type, () => dropzone.classList.add('dragging')));
['dragleave', 'drop'].forEach(type => dropzone.addEventListener(type, () => dropzone.classList.remove('dragging')));

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
    const blob = await response.blob();
    const disposition = response.headers.get('content-disposition') || '';
    const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)/i);
    const name = match ? decodeURIComponent(match[1].replace(/"/g, '')) : 'processed_invoice.zip';
    const url = URL.createObjectURL(blob);
    const link = Object.assign(document.createElement('a'), { href: url, download: name });
    link.click();
    URL.revokeObjectURL(url);
    message.className = 'message success';
    message.textContent = 'Done — your Order Ref CSV bundle has downloaded.';
  } catch (error) {
    message.className = 'message error';
    message.textContent = error.message;
  } finally {
    button.disabled = false;
    button.classList.remove('working');
  }
});
