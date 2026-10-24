export { CONSENT_TEXT, personalConsents, type AnyConsentType, type CompanyConsents, type ConsentReminder } from './model/consents'
export {
  founderPrescreen,
  prescreenPassed,
  projectApproved,
  projectOutdated,
  type CompanyStartupInfo,
  type FounderPrescreen,
} from './model/prescreen'
export { customer, customerName, isClientAccount, useCustomer } from './model/session'
export { default as FounderPrescreenPanel } from './ui/FounderPrescreenPanel.vue'
export { default as PersonalConsentPrompt } from './ui/PersonalConsentPrompt.vue'
