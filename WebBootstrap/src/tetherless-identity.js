// Source-derived defaults from the pinned Tetherless native build, not isideload's
// generic signing-time renaming. Actual IPA identities are always preserved.
export function tetherlessGroup(bundles) {
  const root = bundles[0]?.id;
  if (!/^org\.tetherless\.Tetherless(?:\.[A-Z0-9]{10})?$/.test(root || '')) return null;
  const permitted = new Set([root, `${root}.AltWidget`, `${root}.SideBackup`]);
  if (bundles.some((bundle) => !permitted.has(bundle.id))) throw new Error('This Tetherless IPA has an unrecognized nested bundle. Verify the build before provisioning.');
  return { identifier: `group.${root}`, name: 'Tetherless shared data' };
}
