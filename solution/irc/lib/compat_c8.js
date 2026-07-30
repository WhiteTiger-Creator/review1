export function compatOk(profile, ckpt) {
  return profile.tokenizer_id === ckpt.tokenizer_id && profile.adapter_id === ckpt.adapter_id;
}
