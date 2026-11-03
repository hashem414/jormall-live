# Karmalite doctor configuration

Doctors are explicit Karmalite service-provider configurations. A staff role, title, or `isBookable`
value does not make a staff member a doctor.

Authorized owners use `/{locale}/business/doctors` to configure an existing tenant team member with
an English and Arabic display name, optional public contact details, profession, specialty, active
and bookable state, assigned branches, and assigned services. The repository validates every branch,
service, membership, and doctor identifier inside the authenticated tenant and writes an audit
event. No organization ID is accepted from the browser.

Only active, bookable doctors assigned to both the selected branch and service appear as booking
options. Deactivation is soft; appointment history is retained. The phase does not fabricate doctor
names, qualifications, licenses, or schedules.

The page also exposes the configured weekly schedule, breaks, date-specific leave, and appointment
links according to the viewer's actual grants. The role name remains independent of the explicit
doctor flag so custom-role permissions continue to work.
