export class AuroraError extends Error {
  constructor(message, { code = 'AURORA_ERROR', details = undefined } = {}) {
    super(message);
    this.name = 'AuroraError';
    this.code = code;
    this.details = details;
  }
}

export function isAuroraError(err) {
  return err instanceof AuroraError;
}
