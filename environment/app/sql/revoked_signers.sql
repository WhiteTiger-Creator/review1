SELECT signer_id, public_key_sha256
FROM trusted_signers
WHERE status = 'revoked'
ORDER BY signer_id;
