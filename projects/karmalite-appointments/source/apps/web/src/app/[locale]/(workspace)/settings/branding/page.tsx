import SettingsPage from "../../../dashboard/settings/page";

export default async function BrandingSettingsPage(
  properties: PageProps<"/[locale]/settings/branding">,
) {
  const query = await properties.searchParams;
  return SettingsPage({
    params: properties.params,
    searchParams: Promise.resolve({ ...query, section: "branding" }),
  });
}
