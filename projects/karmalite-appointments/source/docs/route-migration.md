# Karmalite route migration checkpoint

The full operational specification remains in progress. These are the routes actually changed in the
initial delivery, not a list of implemented future modules.

| Route, after locale prefix                                                                       | Current behavior                                                                                                                                                   |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/schedule/today`, `/schedule/calendar`, `/schedule/appointments`, `/schedule/waitlist`          | Existing protected scheduling screens remain canonical. Shared tab links carry valid date, branch, provider, service, room, search and open-appointment selectors. |
| `/ai-studio/knowledge`, `/behavior`, `/actions`, `/usage`, `/test` under AI Studio               | Retired; render not found.                                                                                                                                         |
| `/dashboard/knowledge`, `/dashboard/ai-settings`, `/dashboard/ai-actions`, `/dashboard/ai-usage` | Existing redirects lead to the retired screens; no bypass.                                                                                                         |
| `/inbox?tab=handoffs`, `/dashboard/ai-handoffs`                                                  | Retired; render not found, not an ordinary conversation tab.                                                                                                       |
| `/inbox?tab=conversations`, `/inbox?tab=messages`, `/inbox?tab=delivery-issues`                  | Retained with existing independent repository permissions.                                                                                                         |
| `/settings/channels`                                                                             | Retained; channel configuration and verified customer transports are not retired.                                                                                  |

Existing mappings in `ui-ux-route-migration.md` remain valid except AI Studio and Handoffs
destinations above. No browser-supplied organization or role is propagated. Tab transitions drop
success/error messages, pagination, view-specific tabs and credentials; appointment status is not
interpreted as waiting-list status. Repeated or malformed selectors are discarded independently.
Backend validation and session tenant resolution remain authoritative.

The recommended `/patients`, `/doctors`, `/inventory`, `/chatbot-escalations` and `/notifications`
routes are not implemented in this checkpoint. They must be added with their authorized workflows,
not presented as empty functioning modules.
