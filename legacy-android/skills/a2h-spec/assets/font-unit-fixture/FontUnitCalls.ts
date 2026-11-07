declare const fontFixture: TextAttribute;
fontFixture.fontSize('18vp');
fontFixture.fontSize('18fp');
fontFixture.fontSize(18);
// @ts-expect-error: a valid probe must check the SDK signature, not an any shim
fontFixture.fontSize({});
