Nimbus is a managed job-scheduling platform launched in 2021. It runs customer workloads in isolated containers called pods.

The Starter plan costs 19 dollars per month and includes 5 concurrent pods. The Team plan costs 79 dollars per month and includes 40 concurrent pods. Enterprise pricing is negotiated individually.

When a pod crashes, Nimbus restarts it automatically up to 4 times, waiting 15 seconds before the first retry and doubling the wait each time. After the fourth failure the job is moved to the quarantine list.

Execution logs are kept for 30 days on the Starter plan and 180 days on the Team plan. Logs older than the limit are deleted every night at 02:00 UTC.

All traffic is encrypted with TLS 1.3. Secrets are stored in a vault service and injected into pods as environment variables at start time; they are never written to disk.

Nimbus operates in three regions: Frankfurt, Singapore and Oregon. Customers choose a region when creating a project and cannot change it afterwards.

Support tickets receive a first response within 8 business hours on Starter and within 1 hour on Team. Enterprise customers get a dedicated engineer reachable by phone.

The public API allows 600 requests per minute per project. Requests above that limit receive HTTP status 429 together with a Retry-After header.

Jobs can be scheduled with cron expressions or with a fixed delay. The shortest supported interval is 30 seconds, and the longest delay is 90 days.

Invoices are issued on the first day of each month. Unused pod capacity does not roll over, but payments made by annual prepayment receive a 15 percent discount.

The dashboard shows queue depth, job duration percentiles and failure counts. Alerts can be delivered by email or by webhook, and the default alert threshold is a failure rate above 5 percent over 10 minutes.

When a project is deleted, its data is kept in a recovery area for 14 days before permanent removal.
