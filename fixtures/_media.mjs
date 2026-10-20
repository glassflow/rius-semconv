// Media payloads shared by the recorders: tiny, deterministic and valid enough
// for a provider client to accept. Built from code, never read from disk, so a
// re-recording is byte-identical. The same payloads as _media.py, byte for byte
// (tests/test_media_payloads.py compares them).

import { crc32, deflateSync } from "node:zlib";

const chunk = (kind, body) => {
  const kindBytes = Buffer.from(kind, "latin1");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(body.length);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([kindBytes, body])) >>> 0);
  return Buffer.concat([length, kindBytes, body, crc]);
};

const png = () => {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(1, 0); // width
  header.writeUInt32BE(1, 4); // height
  header.set([8, 0, 0, 0, 0], 8); // 8-bit grayscale
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(Buffer.from([0, 0]), { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
};

/** A 1x1 grayscale PNG, 67 bytes. */
export const PNG_1X1 = png();
if (PNG_1X1.length !== 67) throw new Error(`PNG_1X1 is ${PNG_1X1.length} bytes`);

/** A PNG-headed buffer whose base64 form has more than `minB64Chars`
 * characters: the PNG signature and a valid header, then zero padding. */
export const bigPng = (minB64Chars) => {
  const size = (Math.floor(minB64Chars / 4) + 1) * 3;
  const head = PNG_1X1.subarray(0, 33); // signature and IHDR
  return Buffer.concat([head, Buffer.alloc(size - head.length)]);
};

const wav = () => {
  const rate = 8000;
  const data = Buffer.alloc(800 * 2); // 0.1 s of 16-bit mono silence
  const u32 = (n) => {
    const b = Buffer.alloc(4);
    b.writeUInt32LE(n);
    return b;
  };
  const fmt = Buffer.alloc(16);
  fmt.writeUInt16LE(1, 0);
  fmt.writeUInt16LE(1, 2);
  fmt.writeUInt32LE(rate, 4);
  fmt.writeUInt32LE(rate * 2, 8);
  fmt.writeUInt16LE(2, 12);
  fmt.writeUInt16LE(16, 14);
  return Buffer.concat([
    Buffer.from("RIFF"),
    u32(36 + data.length),
    Buffer.from("WAVEfmt "),
    u32(fmt.length),
    fmt,
    Buffer.from("data"),
    u32(data.length),
    data,
  ]);
};

/** 0.1 s of silence, 8 kHz 16-bit mono WAV. */
export const WAV_SILENT = wav();

const pdf = () => {
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] >>",
  ];
  let out = "%PDF-1.4\n";
  const offsets = [];
  objects.forEach((body, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = out.length;
  const pad = (n) => String(n).padStart(10, "0");
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) out += `${pad(offset)} 00000 n \n`;
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
};

/** A minimal one-page PDF. */
export const PDF_ONE_PAGE = pdf();

export const b64 = (data) => Buffer.from(data).toString("base64");

export const dataUrl = (mime, data) => `data:${mime};base64,${b64(data)}`;
