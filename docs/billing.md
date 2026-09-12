# Billing

Create a recurring Stripe price and supply the secret key, recognized price ID and endpoint webhook secret. Use test mode first. Configure the customer portal for the intended upgrades, downgrades, cancellation and payment methods. The UI delegates these changes to Stripe's hosted portal.

Register `/api/v1/webhooks/stripe` for `customer.subscription.created`, `customer.subscription.updated` and `customer.subscription.deleted`. The implementation verifies the raw body/signature and five-minute timestamp window using Stripe's SDK, consistent with [Stripe webhook verification guidance](https://docs.stripe.com/webhooks).

Checkout creates one idempotent customer per organization and a session using a caller request UUID scoped to that organization. Existing active subscriptions go to the portal rather than creating a second subscription. Return URLs are server-configured. Returning from Checkout does not grant entitlement.

Webhook IDs have a unique key. Processing and subscription changes commit together. Old events do not regress state; accepted events read canonical Stripe subscription state. Unknown price IDs restrict the plan. Trial state is created server-side for new accounts; active/trialing status and an unexpired trial are required for provider AI invocation.

AI requests/tokens, processed emails/documents, actions and workflows are metered. CRM access is not currently suspended by a billing failure; the implemented entitlement gate controls remote AI usage. Plan catalogs with different feature limits, prorations beyond the Stripe portal, tax configuration, dunning policy and live checkout certification remain launch work. No demo charge or real checkout was made during this build.

## Checkout and subscription reconciliation

One pending checkout attempt per workspace is stored durably before calling Stripe, including its idempotency key and exact request parameters. Subsequent browser UUIDs reuse an open session. Timeouts reuse the same attempt even after settings change. Completed checkout goes to the portal while webhook processing catches up. A replacement session requires provider-confirmed expiration, or a completed session linked to a provider-confirmed canceled subscription. Current subscription status is fetched before permitting another checkout.

An unresolved attempt older than 23 hours stops with `billing_checkout_reconcile`; it is never blindly replayed after the provider's key-retention window. This follows [Stripe idempotency semantics](https://docs.stripe.com/api/idempotent_requests) and [Checkout session status](https://docs.stripe.com/api/checkout/sessions/object). An operator with Stripe test/dashboard access must locate the request by its stored idempotency key and customer. Recover the returned session ID into the existing checkout state, or confirm the session expired and no subscription was created before clearing that pending attempt under a maintenance transaction. Do not clear ambiguous attempts merely to enable another payment.

Terminal events for an older subscription cannot overwrite the current subscription or advance its event watermark. A replacement active subscription is accepted only after its tracked predecessor is confirmed terminal at Stripe; two open subscriptions produce a reconciliation conflict and the event receipt is rolled back for redelivery. No code silently cancels a customer's subscription to resolve a conflict. These paths have simulated provider tests; real test-mode payment and webhook acceptance remain pending.
