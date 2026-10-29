// Force an ad hoc identity: the builder's certificate lookup can treat "-"
// as a substring and select an unrelated developer's keychain certificate.
exports.sign = async function sign(options) {
  const { signAsync } = await import("@electron/osx-sign");
  await signAsync({ ...options, identity: "-", identityValidation: false });
};
