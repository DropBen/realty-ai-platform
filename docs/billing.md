# Billing

Create a recurring Stripe price and supply the secret key, recognized price ID and endpoint webhook secret. Use test mode first. Configure the customer portal for the intended upgrades, downgrades, cancellation and payment methods. The UI delegates these changes to Stripe's hosted portal.

Register `/api/v1/webhooks/stripe` for `customer.subscription.created`, `customer.subscription.updated` and `customer.subscription.deleted`. The implementation verifies the raw body/signature and five-minute timestamp window using Stripe's SDK, consistent with [Stripe webhook verification guidance](https://docs.stripe.com/webhooks).

Checkout creates one idempotent customer per organization and a session using a caller request UUID scoped to that organization. Existing active subscriptions go to the portal rather than creating a second subscription. Return URLs are server-configured. Returning from Checkout does not grant entitlement.

Webhook IDs have a unique key. Processing and subscription changes commit together. Old events do not regress state; accepted events read canonical Stripe subscription state. Unknown price IDs restrict the plan. Trial state is created server-side for new accounts; active/trialing status and an unexpired trial are required for provider AI invocation.

AI requests/tokens, processed emails/documents, actions and workflows are metered. CRM access is not currently suspended by a billing failure; the implemented entitlement gate controls remote AI usage. Plan catalogs with different feature limits, prorations beyond the Stripe portal, tax configuration, dunning policy and live checkout certification remain launch work. No demo charge or real checkout was made during this build.
