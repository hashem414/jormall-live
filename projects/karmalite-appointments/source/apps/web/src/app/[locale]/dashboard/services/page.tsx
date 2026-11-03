import { canAccessResource } from "@jormall/auth/tenant-policy";
import { isSupportedLocale } from "@jormall/contracts/locales";
import { notFound } from "next/navigation";

import { DashboardPageHero } from "../../../../components/dashboard-page-hero";
import { Feedback } from "../../../../components/feedback";
import { formatServicePrice } from "../../../../components/service-price";
import { SubmitButton } from "../../../../components/submit-button";
import { ownerWorkspaceMessages } from "../../../../messages/owner-workspace";
import { phaseOneMessages, phaseOneValueLabel } from "../../../../messages/phase-one";
import {
  identityRepository,
  operationalWorkflowsRepository,
  requirePagePermission,
} from "../../../../server/identity";
import {
  configureServiceBranchAction,
  createServiceAction,
  manageServiceRequirementAction,
  updateServiceAction,
} from "../../actions";

export default async function ServicesPage({
  params,
  searchParams,
}: PageProps<"/[locale]/dashboard/services">) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) notFound();
  const [access, query] = await Promise.all([
    requirePagePermission(locale, "services.read"),
    searchParams,
  ]);
  const canManage = canAccessResource(access, "services.manage");
  const canReadInventory = canAccessResource(access, "inventory.items.read");
  const canManageInventory = canAccessResource(access, "inventory.items.manage");
  const [services, branches, inventory, serviceRequirements] = await Promise.all([
    identityRepository.listServices(access),
    identityRepository.listBranches(access),
    canReadInventory ? operationalWorkflowsRepository.listInventory(access) : Promise.resolve(null),
    canReadInventory
      ? operationalWorkflowsRepository.listAllServiceRequirements(access)
      : Promise.resolve([]),
  ]);
  const messages = phaseOneMessages[locale];
  const workspace = ownerWorkspaceMessages[locale];
  const workspaceBranches = access.activeBranchId
    ? branches.filter(({ id }) => id === access.activeBranchId)
    : branches;
  const enabledConfigurations = services
    .flatMap((service) => service.branches)
    .filter((configuration) => configuration.isEnabled);
  const coveredBranches = new Set(enabledConfigurations.map(({ branchId }) => branchId)).size;
  const averageDuration =
    services.length === 0
      ? 0
      : Math.round(
          services.reduce((total, service) => total + service.defaultDurationMins, 0) /
            services.length,
        );
  const search = typeof query.q === "string" ? query.q.trim().slice(0, 100) : "";
  const status = query.status === "APPROVED" || query.status === "DRAFT" ? query.status : "";
  const visibleServices = services.filter((service) => {
    const searchText = [service.nameEn, service.nameAr, service.category ?? ""]
      .join(" ")
      .toLocaleLowerCase(locale);
    return (
      (!search || searchText.includes(search.toLocaleLowerCase(locale))) &&
      (!status || service.configurationStatus === status)
    );
  });

  return (
    <section className="page-stack services-workspace" aria-labelledby="services-title">
      <DashboardPageHero
        description={workspace.serviceDescription}
        eyebrow={workspace.workspace}
        icon="◇"
        title={messages.services}
        titleId="services-title"
      />
      <Feedback
        error={typeof query.error === "string" ? query.error : undefined}
        locale={locale}
        notice={typeof query.notice === "string" ? query.notice : undefined}
      />

      <dl className="workspace-metrics">
        <div>
          <span aria-hidden="true">◇</span>
          <dt>{workspace.serviceCount}</dt>
          <dd>{services.length}</dd>
        </div>
        <div>
          <span aria-hidden="true">⌂</span>
          <dt>{workspace.branchCoverage}</dt>
          <dd>
            {coveredBranches}/{workspaceBranches.length}
          </dd>
        </div>
        <div>
          <span aria-hidden="true">✓</span>
          <dt>{workspace.enabledBranches}</dt>
          <dd>{enabledConfigurations.length}</dd>
        </div>
        <div>
          <span aria-hidden="true">◷</span>
          <dt>{workspace.averageDuration}</dt>
          <dd>
            {averageDuration} <small>{workspace.minutesShort}</small>
          </dd>
        </div>
      </dl>

      {canManage ? (
        <details className="panel action-disclosure workspace-action">
          <summary>+ {workspace.addServiceSummary}</summary>
          <div className="disclosure-heading">
            <h2>{workspace.addServiceSummary}</h2>
            <p>{workspace.addServiceDescription}</p>
          </div>
          <form action={createServiceAction} className="form-grid workspace-form">
            <input name="locale" type="hidden" value={locale} />
            <label className="field">
              <span className="field-label">{messages.englishName}</span>
              <input className="input" name="nameEn" required />
            </label>
            <label className="field">
              <span className="field-label">{workspace.arabicName}</span>
              <input className="input" dir="rtl" name="nameAr" required />
            </label>
            <InstructionField label={workspace.descriptionEn} name="descriptionEn" />
            <InstructionField dir="rtl" label={workspace.descriptionAr} name="descriptionAr" />
            <label className="field">
              <span className="field-label">{messages.defaultDuration}</span>
              <input
                className="input"
                min={1}
                max={1440}
                name="defaultDurationMins"
                required
                type="number"
              />
            </label>
            <label className="field">
              <span className="field-label">{locale === "ar" ? "الفئة" : "Category"}</span>
              <input className="input" name="category" required />
            </label>
            <label className="field">
              <span className="field-label">{workspace.priceMinorLabel}</span>
              <input className="input" min={0} name="defaultPriceMinor" type="number" />
              <small className="field-hint">{workspace.priceMinorHint}</small>
            </label>
            <label className="field">
              <span className="field-label">{messages.currency}</span>
              <input
                className="input"
                defaultValue="JOD"
                dir="ltr"
                maxLength={3}
                name="currency"
                required
              />
            </label>
            <label className="field">
              <span className="field-label">
                {locale === "ar" ? "الحد الأدنى للإشعار (دقيقة)" : "Minimum notice (minutes)"}
              </span>
              <input className="input" min={0} name="minimumNoticeMins" type="number" />
              <small className="field-hint">{workspace.leaveBlankIfUnconfigured}</small>
            </label>
            <label className="check-field">
              <input name="isOnlineBookable" type="checkbox" />
              <span>{locale === "ar" ? "متاحة للحجز عبر الإنترنت" : "Online bookable"}</span>
            </label>
            <InstructionField
              label={
                locale === "ar"
                  ? "تعليمات ما قبل العلاج (بالإنجليزية)"
                  : "Pre-treatment instructions (English)"
              }
              name="preTreatmentInstructionsEn"
            />
            <InstructionField
              dir="rtl"
              label={
                locale === "ar"
                  ? "تعليمات ما قبل العلاج (بالعربية)"
                  : "Pre-treatment instructions (Arabic)"
              }
              name="preTreatmentInstructionsAr"
            />
            <InstructionField
              label={
                locale === "ar"
                  ? "تعليمات ما بعد العلاج (بالإنجليزية)"
                  : "Post-treatment instructions (English)"
              }
              name="postTreatmentInstructionsEn"
            />
            <InstructionField
              dir="rtl"
              label={
                locale === "ar"
                  ? "تعليمات ما بعد العلاج (بالعربية)"
                  : "Post-treatment instructions (Arabic)"
              }
              name="postTreatmentInstructionsAr"
            />
            <div className="form-actions">
              <SubmitButton>{messages.addService}</SubmitButton>
            </div>
          </form>
        </details>
      ) : null}

      <div className="section-heading workspace-section-heading">
        <div>
          <p className="eyebrow">{workspace.businessSetup}</p>
          <h2>{workspace.allServices}</h2>
        </div>
        <span className="section-count">
          {visibleServices.length}/{services.length}
        </span>
      </div>
      <form
        action={`/${locale}/business/services`}
        className="filter-toolbar service-filter-toolbar"
      >
        <label className="field filter-search">
          <span className="field-label">
            {locale === "ar" ? "البحث في الخدمات" : "Search services"}
          </span>
          <input
            className="input"
            defaultValue={search}
            name="q"
            placeholder={locale === "ar" ? "الاسم أو الفئة" : "Name or category"}
            type="search"
          />
        </label>
        <label className="field">
          <span className="field-label">{messages.status}</span>
          <select className="select" defaultValue={status} name="status">
            <option value="">{locale === "ar" ? "كل الحالات" : "All statuses"}</option>
            <option value="APPROVED">{workspace.approvedStatus}</option>
            <option value="DRAFT">{workspace.draftStatus}</option>
          </select>
        </label>
        <SubmitButton tone="secondary">{locale === "ar" ? "تطبيق" : "Apply"}</SubmitButton>
      </form>

      {visibleServices.length === 0 ? (
        <div className="empty-state">
          <span className="empty-state-icon" aria-hidden="true">
            ◇
          </span>
          <h2>{workspace.noServices}</h2>
          <p>{workspace.noServicesDescription}</p>
        </div>
      ) : (
        <div className="service-program-grid">
          {visibleServices.map((service) => {
            const enabled = service.branches.filter((configuration) => configuration.isEnabled);
            const preTreatmentInstructions =
              locale === "ar"
                ? service.preTreatmentInstructionsAr
                : service.preTreatmentInstructionsEn;
            const postTreatmentInstructions =
              locale === "ar"
                ? service.postTreatmentInstructionsAr
                : service.postTreatmentInstructionsEn;
            const materialRequirements = serviceRequirements.filter(
              (requirement) => requirement.serviceId === service.id,
            );
            return (
              <article className="record-card service-program-card" key={service.id}>
                <header className="service-program-heading">
                  <span className="service-program-icon" aria-hidden="true">
                    ◇
                  </span>
                  <div>
                    <h3>{locale === "ar" ? service.nameAr : service.nameEn}</h3>
                    <p>{locale === "ar" ? service.nameEn : service.nameAr}</p>
                  </div>
                  <span
                    className={`status ${service.configurationStatus === "APPROVED" ? "status-active" : "status-pending"}`}
                  >
                    {service.configurationStatus === "APPROVED"
                      ? workspace.approvedStatus
                      : workspace.draftStatus}
                  </span>
                </header>

                {service.descriptionEn || service.descriptionAr ? (
                  <details className="service-description-disclosure">
                    <summary>{locale === "ar" ? "عرض الوصف" : "View description"}</summary>
                    <p dir={locale === "ar" ? "rtl" : undefined}>
                      {locale === "ar" ? service.descriptionAr : service.descriptionEn}
                    </p>
                  </details>
                ) : null}

                {preTreatmentInstructions || postTreatmentInstructions ? (
                  <details className="service-description-disclosure service-instructions-disclosure">
                    <summary>
                      {locale === "ar" ? "تعليمات العلاج" : "Treatment instructions"}
                    </summary>
                    <div className="service-instruction-list">
                      {preTreatmentInstructions ? (
                        <div>
                          <strong>{locale === "ar" ? "قبل العلاج" : "Before treatment"}</strong>
                          <p>{preTreatmentInstructions}</p>
                        </div>
                      ) : null}
                      {postTreatmentInstructions ? (
                        <div>
                          <strong>{locale === "ar" ? "بعد العلاج" : "After treatment"}</strong>
                          <p>{postTreatmentInstructions}</p>
                        </div>
                      ) : null}
                    </div>
                  </details>
                ) : null}

                <dl className="service-facts">
                  <div
                    className={
                      service.defaultPriceMinor === null ? "service-price-unpublished" : undefined
                    }
                  >
                    <dt>{workspace.basePrice}</dt>
                    <dd>
                      {formatServicePrice(locale, service.defaultPriceMinor, service.currency)}
                    </dd>
                  </div>
                  <div>
                    <dt>{workspace.duration}</dt>
                    <dd>
                      {service.defaultDurationMins} {workspace.minutesLong}
                      {service.configurationStatus === "DRAFT"
                        ? ` — ${workspace.provisionalStatus}`
                        : ""}
                    </dd>
                  </div>
                  <div>
                    <dt>{locale === "ar" ? "الفئة" : "Category"}</dt>
                    <dd>{service.category ?? (locale === "ar" ? "غير مصنفة" : "Uncategorized")}</dd>
                  </div>
                  <div>
                    <dt>{locale === "ar" ? "الحجز عبر الإنترنت" : "Online booking"}</dt>
                    <dd>{phaseOneValueLabel(locale, service.isOnlineBookable ? "ON" : "OFF")}</dd>
                  </div>
                  <div>
                    <dt>{workspace.enabledBranches}</dt>
                    <dd>
                      {enabled.length}/{workspaceBranches.length}
                    </dd>
                  </div>
                  <div>
                    <dt>{locale === "ar" ? "الأطباء المعيّنون" : "Assigned doctors"}</dt>
                    <dd>
                      {service.staffServices
                        .map(({ staffProfile }) =>
                          locale === "ar" ? staffProfile.displayNameAr : staffProfile.displayNameEn,
                        )
                        .join(", ") ||
                        (locale === "ar" ? "لم يتم تعيين أطباء" : "No doctors assigned")}
                    </dd>
                  </div>
                  <div>
                    <dt>{locale === "ar" ? "الغرف المتوافقة" : "Compatible rooms"}</dt>
                    <dd>
                      {service.roomCompatibilities
                        .map(({ resource }) =>
                          locale === "ar" ? resource.nameAr : resource.nameEn,
                        )
                        .join(", ") ||
                        (locale === "ar"
                          ? "لم يتم إعداد غرف متوافقة"
                          : "No compatible rooms configured")}
                    </dd>
                  </div>
                </dl>

                {canReadInventory ? (
                  <details className="inline-disclosure service-materials-disclosure">
                    <summary>
                      {locale === "ar" ? "مواد الخدمة والمخزون" : "Service materials & inventory"}
                      {materialRequirements.length > 0 ? ` (${materialRequirements.length})` : ""}
                    </summary>
                    <p className="muted">
                      {locale === "ar"
                        ? "حدد المواد المتوقعة لهذه الخدمة وكيفية حجزها للمواعيد."
                        : "Define the materials expected for this service and when stock is reserved."}
                    </p>
                    {materialRequirements.length === 0 ? (
                      <p className="muted">
                        {locale === "ar"
                          ? "لم تتم إضافة مواد لهذه الخدمة."
                          : "No materials are configured for this service."}
                      </p>
                    ) : (
                      <ul className="branch-configs service-material-list">
                        {materialRequirements.map((requirement) => (
                          <li key={requirement.id}>
                            <span>
                              <strong>{requirement.item.name}</strong>
                              <small>
                                {Number(requirement.expectedQuantity)} {requirement.unitOfMeasure}
                                {" · "}
                                {requirement.reservationMode === "RESERVE_ON_CONFIRMATION"
                                  ? locale === "ar"
                                    ? "حجز عند تأكيد الموعد"
                                    : "Reserve when confirmed"
                                  : requirement.reservationMode === "FORECAST_ONLY"
                                    ? locale === "ar"
                                      ? "للتوقع فقط"
                                      : "Forecast only"
                                    : locale === "ar"
                                      ? "بدون حجز"
                                      : "No reservation"}
                              </small>
                            </span>
                            {canManageInventory ? (
                              <form action={manageServiceRequirementAction}>
                                <input name="actionType" type="hidden" value="REMOVE" />
                                <input name="id" type="hidden" value={requirement.id} />
                                <input name="locale" type="hidden" value={locale} />
                                <input
                                  name="returnTo"
                                  type="hidden"
                                  value={`/${locale}/business/services`}
                                />
                                <SubmitButton tone="danger">
                                  {locale === "ar" ? "إزالة" : "Remove"}
                                </SubmitButton>
                              </form>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    )}
                    {canManageInventory && inventory && inventory.items.length > 0 ? (
                      <form action={manageServiceRequirementAction} className="compact-form">
                        <input name="locale" type="hidden" value={locale} />
                        <input name="serviceId" type="hidden" value={service.id} />
                        <input
                          name="returnTo"
                          type="hidden"
                          value={`/${locale}/business/services`}
                        />
                        <label className="field">
                          <span className="field-label">
                            {locale === "ar" ? "صنف المخزون" : "Inventory item"}
                          </span>
                          <select className="select" name="itemId" required>
                            {inventory.items
                              .filter((item) => item.isActive)
                              .map((item) => (
                                <option key={item.id} value={item.id}>
                                  {item.name} ({item.unitOfMeasure})
                                </option>
                              ))}
                          </select>
                        </label>
                        <label className="field">
                          <span className="field-label">
                            {locale === "ar" ? "الكمية المتوقعة" : "Expected quantity"}
                          </span>
                          <input
                            className="input"
                            min="0.001"
                            name="expectedQuantity"
                            required
                            step="0.001"
                            type="number"
                          />
                        </label>
                        <label className="field">
                          <span className="field-label">
                            {locale === "ar" ? "وحدة القياس" : "Unit of measure"}
                          </span>
                          <input className="input" name="unitOfMeasure" required />
                        </label>
                        <label className="field">
                          <span className="field-label">
                            {locale === "ar" ? "سياسة الحجز" : "Reservation policy"}
                          </span>
                          <select
                            className="select"
                            defaultValue="FORECAST_ONLY"
                            name="reservationMode"
                          >
                            <option value="NONE">
                              {locale === "ar" ? "بدون حجز" : "No reservation"}
                            </option>
                            <option value="FORECAST_ONLY">
                              {locale === "ar" ? "للتوقع فقط" : "Forecast only"}
                            </option>
                            <option value="RESERVE_ON_CONFIRMATION">
                              {locale === "ar" ? "حجز عند تأكيد الموعد" : "Reserve when confirmed"}
                            </option>
                          </select>
                        </label>
                        <label className="check-field">
                          <input defaultChecked name="isRequired" type="checkbox" />
                          <span>{locale === "ar" ? "مادة مطلوبة" : "Required material"}</span>
                        </label>
                        <div className="form-actions">
                          <SubmitButton>
                            {locale === "ar" ? "حفظ المادة" : "Save material"}
                          </SubmitButton>
                        </div>
                      </form>
                    ) : null}
                  </details>
                ) : null}

                {canManage ? (
                  <details className="inline-disclosure">
                    <summary>{locale === "ar" ? "تعديل الخدمة" : "Edit service"}</summary>
                    <form action={updateServiceAction} className="form-grid">
                      <input name="locale" type="hidden" value={locale} />
                      <input name="serviceId" type="hidden" value={service.id} />
                      <label className="field">
                        <span className="field-label">{messages.englishName}</span>
                        <input
                          className="input"
                          defaultValue={service.nameEn}
                          name="nameEn"
                          required
                        />
                      </label>
                      <label className="field">
                        <span className="field-label">{workspace.arabicName}</span>
                        <input
                          className="input"
                          defaultValue={service.nameAr}
                          dir="rtl"
                          name="nameAr"
                          required
                        />
                      </label>
                      <InstructionField
                        label={workspace.descriptionEn}
                        name="descriptionEn"
                        value={service.descriptionEn ?? ""}
                      />
                      <InstructionField
                        dir="rtl"
                        label={workspace.descriptionAr}
                        name="descriptionAr"
                        value={service.descriptionAr ?? ""}
                      />
                      <label className="field">
                        <span className="field-label">{messages.defaultDuration}</span>
                        <input
                          className="input"
                          defaultValue={service.defaultDurationMins}
                          max={1440}
                          min={1}
                          name="defaultDurationMins"
                          required
                          type="number"
                        />
                      </label>
                      <label className="field">
                        <span className="field-label">
                          {locale === "ar" ? "الفئة" : "Category"}
                        </span>
                        <input
                          className="input"
                          defaultValue={service.category ?? "Beauty Treatment"}
                          name="category"
                          required
                        />
                      </label>
                      <label className="field">
                        <span className="field-label">
                          {locale === "ar" ? "حالة الاعتماد" : "Approval status"}
                        </span>
                        <select
                          className="select"
                          defaultValue={service.configurationStatus}
                          name="configurationStatus"
                        >
                          <option value="DRAFT">{workspace.draftStatus}</option>
                          <option value="APPROVED">{workspace.approvedStatus}</option>
                        </select>
                      </label>
                      <label className="field">
                        <span className="field-label">
                          {locale === "ar"
                            ? "الحد الأدنى للإشعار (دقيقة)"
                            : "Minimum notice (minutes)"}
                        </span>
                        <input
                          className="input"
                          defaultValue={service.minimumNoticeMins ?? ""}
                          min={0}
                          name="minimumNoticeMins"
                          type="number"
                        />
                      </label>
                      <InstructionField
                        label={
                          locale === "ar"
                            ? "تعليمات ما قبل العلاج (بالإنجليزية)"
                            : "Pre-treatment instructions (English)"
                        }
                        name="preTreatmentInstructionsEn"
                        value={service.preTreatmentInstructionsEn ?? ""}
                      />
                      <InstructionField
                        dir="rtl"
                        label={
                          locale === "ar"
                            ? "تعليمات ما قبل العلاج (بالعربية)"
                            : "Pre-treatment instructions (Arabic)"
                        }
                        name="preTreatmentInstructionsAr"
                        value={service.preTreatmentInstructionsAr ?? ""}
                      />
                      <InstructionField
                        label={
                          locale === "ar"
                            ? "تعليمات ما بعد العلاج (بالإنجليزية)"
                            : "Post-treatment instructions (English)"
                        }
                        name="postTreatmentInstructionsEn"
                        value={service.postTreatmentInstructionsEn ?? ""}
                      />
                      <InstructionField
                        dir="rtl"
                        label={
                          locale === "ar"
                            ? "تعليمات ما بعد العلاج (بالعربية)"
                            : "Post-treatment instructions (Arabic)"
                        }
                        name="postTreatmentInstructionsAr"
                        value={service.postTreatmentInstructionsAr ?? ""}
                      />
                      <label className="check-field">
                        <input
                          defaultChecked={service.isOnlineBookable}
                          name="isOnlineBookable"
                          type="checkbox"
                        />
                        <span>
                          {locale === "ar" ? "متاحة للحجز عبر الإنترنت" : "Online bookable"}
                        </span>
                      </label>
                      <label className="check-field">
                        <input defaultChecked={service.isActive} name="isActive" type="checkbox" />
                        <span>{locale === "ar" ? "الخدمة نشطة" : "Service active"}</span>
                      </label>
                      <div className="form-actions">
                        <SubmitButton>
                          {locale === "ar" ? "حفظ الخدمة" : "Save service"}
                        </SubmitButton>
                      </div>
                    </form>
                  </details>
                ) : null}

                <ul className="branch-configs service-branch-list">
                  {service.branches.map((configuration) => (
                    <li key={configuration.branchId}>
                      <span>
                        {locale === "ar"
                          ? configuration.branch.nameAr
                          : configuration.branch.nameEn}
                      </span>
                      <small>
                        {phaseOneValueLabel(locale, configuration.isEnabled ? "ON" : "OFF")} ·{" "}
                        {formatServicePrice(
                          locale,
                          configuration.priceMinor ?? service.defaultPriceMinor,
                          service.currency,
                        )}
                        {" · "}
                        {configuration.durationMins ?? service.defaultDurationMins}{" "}
                        {workspace.minutesLong}
                      </small>
                    </li>
                  ))}
                </ul>

                {canManage && workspaceBranches.length > 0 ? (
                  <details className="inline-disclosure">
                    <summary>{workspace.branchSettings}</summary>
                    <p className="muted">{workspace.branchSettingsDescription}</p>
                    <form action={configureServiceBranchAction} className="compact-form">
                      <input name="locale" type="hidden" value={locale} />
                      <input name="serviceId" type="hidden" value={service.id} />
                      <label className="field">
                        <span className="field-label">{messages.branch}</span>
                        <input name="branchId" type="hidden" value={workspaceBranches[0]?.id} />
                        <span className="input" aria-readonly="true">
                          {locale === "ar"
                            ? workspaceBranches[0]?.nameAr
                            : workspaceBranches[0]?.nameEn}
                        </span>
                      </label>
                      <label className="field">
                        <span className="field-label">{messages.priceOverride}</span>
                        <input className="input" min={0} name="priceMinor" type="number" />
                      </label>
                      <label className="field">
                        <span className="field-label">{messages.durationOverride}</span>
                        <input
                          className="input"
                          min={1}
                          max={1440}
                          name="durationMins"
                          type="number"
                        />
                      </label>
                      <label className="field">
                        <span className="field-label">
                          {locale === "ar" ? "فاصل قبل الموعد (دقيقة)" : "Buffer before (minutes)"}
                        </span>
                        <input
                          className="input"
                          defaultValue={0}
                          min={0}
                          name="bufferBeforeMins"
                          required
                          type="number"
                        />
                      </label>
                      <label className="field">
                        <span className="field-label">
                          {locale === "ar" ? "فاصل بعد الموعد (دقيقة)" : "Buffer after (minutes)"}
                        </span>
                        <input
                          className="input"
                          defaultValue={0}
                          min={0}
                          name="bufferAfterMins"
                          required
                          type="number"
                        />
                      </label>
                      <label className="field">
                        <span className="field-label">
                          {locale === "ar"
                            ? "نافذة الحجز للفرع (أيام)"
                            : "Branch booking window (days)"}
                        </span>
                        <input
                          className="input"
                          min={1}
                          max={730}
                          name="bookingWindowDays"
                          type="number"
                        />
                      </label>
                      <label className="check-field">
                        <input defaultChecked name="isEnabled" type="checkbox" />
                        <span>{messages.enabledAtBranch}</span>
                      </label>
                      <SubmitButton tone="secondary">{messages.configure}</SubmitButton>
                    </form>
                  </details>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function InstructionField({
  dir,
  label,
  name,
  value,
}: Readonly<{
  dir?: "rtl";
  label: string;
  name: string;
  value?: string;
}>) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <textarea className="input" defaultValue={value} dir={dir} name={name} rows={3} />
    </label>
  );
}
