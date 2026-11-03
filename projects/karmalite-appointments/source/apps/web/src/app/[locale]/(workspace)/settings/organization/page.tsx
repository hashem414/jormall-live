import SettingsPage from "../../../dashboard/settings/page";

export default async function OrganizationSettingsPage(
  properties: PageProps<"/[locale]/settings/organization">,
) {
  const query = await properties.searchParams;
  return SettingsPage({
    params: properties.params,
    searchParams: Promise.resolve({ ...query, section: "organization" }),
  });
}
