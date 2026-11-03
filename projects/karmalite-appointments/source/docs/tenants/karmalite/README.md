# Karmalite tenant customization

This customization provisions Karmalite as a BEAUTY_CENTER. “Medical Esthetic” is retained only as
part of the official brand name; it does not enable a clinic sector or medical modules.

## Active scope

- One Sweifieh branch
- Five approved beauty-center services
- Unpublished/null prices with an exact English and Arabic contact response
- Karmalite branding and bundled official logo
- Bilingual customer knowledge
- Non-clinical AI boundary enforcement
- Invitation-only Owner activation

The root Karmalite_Chatbot_Knowledge_Base.docx remains unchanged and is not ingested.

## Secure provisioning configuration

Set these only in the deployment environment or an uncommitted local .env:

- KARMALITE_OWNER_EMAIL — provisional invited Owner email, verified out of band before production
- KARMALITE_PROVISIONING_ADMIN_EMAIL — an existing JorMall platform super administrator
- DEV_SEED_PASSWORD — optional development-only bootstrap credential for the reserved
  example.invalid provisioning administrator; never used for the Karmalite Owner

Run pnpm provision:karmalite. The command prints a one-time invitation URL when the tenant has no
active Owner. The invited Owner chooses their own password during activation. No Owner password is
stored in source code or provisioning configuration.

info@karmalite.com is the only public contact email. The Owner email is not written to public
knowledge, branch contact output, widget text, or customer communications.
