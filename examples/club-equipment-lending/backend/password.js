import { argon2, randomBytes, timingSafeEqual } from 'node:crypto';
import { promisify } from 'node:util';

const derive = promisify(argon2);
const parameters = { memory: 65536, passes: 3, parallelism: 1, tagLength: 32 };
const encodedParameters = 'm=65536,t=3,p=1';

async function digest(password, nonce) {
  return derive('argon2id', { ...parameters, message: Buffer.from(password), nonce });
}

export async function hashPassword(password) {
  const nonce = randomBytes(16);
  const tag = await digest(password, nonce);
  return ['$argon2id', 'v=19', encodedParameters, nonce.toString('base64').replace(/=+$/, ''), tag.toString('base64').replace(/=+$/, '')].join('$');
}

export async function verifyPassword(password, hash) {
  const [empty, algorithm, version, settings, salt, encodedTag, ...extra] = hash.split('$');
  if (empty !== '' || algorithm !== 'argon2id' || version !== 'v=19' ||
      settings !== encodedParameters || extra.length || !salt || !encodedTag) return false;
  const nonce = Buffer.from(salt, 'base64');
  const tag = Buffer.from(encodedTag, 'base64');
  return nonce.length === 16 && tag.length === 32 && timingSafeEqual(tag, await digest(password, nonce));
}

