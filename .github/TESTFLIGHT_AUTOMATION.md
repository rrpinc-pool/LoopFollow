# TestFlight build recovery

The upstream build workflow still checks for updates every Sunday and builds on
the second Sunday of each month. `testflight_watchdog.yml` provides an independent
daily check, including manual dispatch for testing.

The watchdog refreshes its own enablement and that of the build workflow through
GitHub's API to prevent inactivity suspension. It requests the existing build
workflow when upstream commits are waiting, an upload is at least 28 days old,
or a newer build attempt failed. It checks the actual TestFlight upload step,
not just a successful workflow status. Upload completion does not prove that
Apple has finished processing the build or made it available to testers.

Running builds are left alone; attempts are separated by at least 24 hours.
Builds pending over six hours and failed attempts still in cooldown fail the
watchdog visibly in Actions. Normal GitHub Actions notification preferences apply.
The watchdog uses only the repository's temporary GITHUB_TOKEN with Actions write
and Contents read access. Signing continues in the original build workflow using
the existing organization secrets.

Keep the watchdog files when merging upstream updates. To pause all automatic
build recovery, disable **Keep TestFlight builds current** before disabling the
normal build workflow. Upstream scheduling can be configured independently with
the existing SCHEDULED_BUILD and SCHEDULED_SYNC repository variables.
