// file-type v17+ is ESM-only (no `require` export), but this file stays
// CommonJS like the rest of the service — so we load it via a cached
// dynamic import() instead of downgrading to the old, vulnerable v16 line
// (GHSA-5v7r-6r5c-r473: infinite loop on malformed ASF input).
let _fileTypeModulePromise;
function getFileTypeModule() {
  if (!_fileTypeModulePromise) {
    _fileTypeModulePromise = import("file-type");
  }
  return _fileTypeModulePromise;
}

// Allowed formats, per the user's spec. Each entry maps the DB's file_type
// enum value to the expected real MIME type(s), so we can cross-check what
// the file actually IS (via magic bytes) against what it claims to be.
const ALLOWED_TYPES = {
  PDF: { mimes: ["application/pdf"], exts: ["pdf"] },
  PNG: { mimes: ["image/png"], exts: ["png"] },
  JPG: { mimes: ["image/jpeg"], exts: ["jpg", "jpeg"] },
  JPEG: { mimes: ["image/jpeg"], exts: ["jpg", "jpeg"] },
  DOCX: {
    mimes: ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
    exts: ["docx"],
  },
  // TXT has no reliable magic bytes (it's just plain text), so it's handled
  // separately below: we only trust it if file-type detects nothing AND the
  // content is valid UTF-8 text with no binary control characters.
  TXT: { mimes: ["text/plain"], exts: ["txt"] },
};

/**
 * Validates an uploaded file against the allowed-format whitelist by
 * inspecting actual file bytes (magic numbers), not just the filename
 * extension or the client-supplied Content-Type — both of which are
 * trivially spoofable. This directly addresses the "restricted formats of
 * acceptance" requirement and the gap found in the reference repo (which had
 * no such check at all).
 *
 * @param {Buffer} buffer - the uploaded file's bytes
 * @param {string} originalFilename
 * @returns {Promise<{ ok: true, file_type: string, mime_type: string } | { ok: false, reason: string }>}
 */
async function validateUpload(buffer, originalFilename) {
  const extFromName = (originalFilename.split(".").pop() || "").toLowerCase();
  const { fileTypeFromBuffer } = await getFileTypeModule();
  const detected = await fileTypeFromBuffer(buffer);

  if (detected) {
    // Binary format detected from magic bytes — find a matching allowed type
    // whose mime list includes what we detected.
    const match = Object.entries(ALLOWED_TYPES).find(([, def]) =>
      def.mimes.includes(detected.mime)
    );
    if (!match) {
      return { ok: false, reason: `Detected file type ${detected.mime} is not allowed` };
    }
    const [fileTypeKey] = match;
    // Also require the extension to be plausible for the detected type, to
    // catch e.g. a renamed .exe disguised as "report.pdf" where the magic
    // bytes AND extension would need to both lie — harder to pull off.
    if (!ALLOWED_TYPES[fileTypeKey].exts.includes(extFromName)) {
      return {
        ok: false,
        reason: `File extension .${extFromName} does not match detected content type ${detected.mime}`,
      };
    }
    return { ok: true, file_type: fileTypeKey, mime_type: detected.mime };
  }

  // No magic bytes detected (expected for plain text). Only allow this path
  // for .txt, and only if the content actually looks like text.
  if (extFromName === "txt") {
    const isLikelyText = isProbablyUtf8Text(buffer);
    if (!isLikelyText) {
      return { ok: false, reason: "File claims to be .txt but contains binary content" };
    }
    return { ok: true, file_type: "TXT", mime_type: "text/plain" };
  }

  return { ok: false, reason: "Could not determine file type, or type is not allowed" };
}

function isProbablyUtf8Text(buffer) {
  // Reject if there are NUL bytes or a high proportion of non-printable
  // control characters in the first chunk — cheap heuristic, good enough to
  // block disguised binaries without a full encoding-detection library.
  const sample = buffer.subarray(0, Math.min(buffer.length, 8000));
  let controlCount = 0;
  for (let i = 0; i < sample.length; i++) {
    const byte = sample[i];
    if (byte === 0) return false;
    const isPrintableAscii = byte >= 32 && byte <= 126;
    const isCommonWhitespace = byte === 9 || byte === 10 || byte === 13;
    const isUtf8Continuation = byte >= 128; // allow multi-byte UTF-8 sequences
    if (!isPrintableAscii && !isCommonWhitespace && !isUtf8Continuation) {
      controlCount++;
    }
  }
  return controlCount / sample.length < 0.01;
}

module.exports = { validateUpload, ALLOWED_TYPES };
