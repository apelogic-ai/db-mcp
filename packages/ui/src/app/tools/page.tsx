import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function ToolsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">MCP Tools</h1>
        <p className="text-gray-400 mt-1">Manage tool exposure to Claude</p>
      </div>

      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            Tool Configuration
            <Badge variant="secondary" className="bg-gray-800 text-gray-300">
              Coming Soon
            </Badge>
          </CardTitle>
          <CardDescription className="text-gray-400">
            Configure which MCP tools are exposed to Claude Desktop. Control
            permissions, set rate limits, and manage tool visibility.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-gray-500 text-sm">
            Available tools will be listed here once a connection is configured.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
