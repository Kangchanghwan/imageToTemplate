// Node 전용: @techstark/opencv-js 로드 후 setCv
import { createRequire } from 'node:module';
import { setCv } from './cv.js';
const require = createRequire(import.meta.url);

export async function loadNodeCv() {
  let cv = require('@techstark/opencv-js');
  if (cv instanceof Promise) cv = await cv;
  else if (!cv.Mat) await new Promise((res) => { cv.onRuntimeInitialized = res; });
  else if (typeof cv.then === 'function') cv = await cv;
  setCv(cv);
  return cv;
}
