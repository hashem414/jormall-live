import SettingsPage from "../../../dashboard/settings/page";

export default async function BookingRulesSettingsPage(
  properties: PageProps<"/[locale]/settings/booking-rules">,
) {
  const query = await properties.searchParams;
  return SettingsPage({
    params: properties.params,
    searchParams: Promise.resolve({ ...query, section: "booking-rules" }),
  });
}
