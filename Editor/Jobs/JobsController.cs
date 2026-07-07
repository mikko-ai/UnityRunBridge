using Mk.UnityAgentBridge.Editor.Routing;

namespace Mk.UnityAgentBridge.Editor.Jobs
{
    internal static class JobsController
    {
        public static void RegisterRoutes()
        {
            CapabilityRegistry.Declare("jobs");
            RouteTable.Register("GET", "jobs/{id}", ctx =>
            {
                JobRecord record = JobManager.GetJob(ctx.PathParam);
                if (record == null)
                {
                    return BridgeResponse.Failure("job_not_found", $"job not found: {ctx.PathParam}");
                }

                return JobManager.BuildJobResponse(record);
            });
        }
    }
}
