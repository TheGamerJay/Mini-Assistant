/**
 * utils/previewImageStore.js
 * IndexedDB-backed store for generated preview images.
 * localStorage silently fails for large base64 strings (>~2MB) due to the 5MB
 * quota — IndexedDB has no practical size limit and survives page refreshes.
 */

const DB_NAME    = 'ma_preview_db';
const STORE_NAME = 'previews';
const DB_VERSION = 1;

function _open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = e => {
      e.target.result.createObjectStore(STORE_NAME);
    };
    req.onsuccess = e => resolve(e.target.result);
    req.onerror   = e => reject(e.target.error);
  });
}

export async function savePreviewImage(chatId, base64) {
  try {
    const db = await _open();
    await new Promise((resolve, reject) => {
      const tx  = db.transaction(STORE_NAME, 'readwrite');
      tx.objectStore(STORE_NAME).put(base64, chatId);
      tx.oncomplete = resolve;
      tx.onerror    = e => reject(e.target.error);
    });
    db.close();
  } catch (err) {
    console.warn('[previewImageStore] save failed:', err);
  }
}

export async function loadPreviewImage(chatId) {
  try {
    const db = await _open();
    const result = await new Promise((resolve, reject) => {
      const tx  = db.transaction(STORE_NAME, 'readonly');
      const req = tx.objectStore(STORE_NAME).get(chatId);
      req.onsuccess = e => resolve(e.target.result || null);
      req.onerror   = e => reject(e.target.error);
    });
    db.close();
    return result;
  } catch (err) {
    console.warn('[previewImageStore] load failed:', err);
    return null;
  }
}

export async function deletePreviewImage(chatId) {
  try {
    const db = await _open();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite');
      tx.objectStore(STORE_NAME).delete(chatId);
      tx.oncomplete = resolve;
      tx.onerror    = e => reject(e.target.error);
    });
    db.close();
  } catch (err) {
    console.warn('[previewImageStore] delete failed:', err);
  }
}
