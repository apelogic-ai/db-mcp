import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function ContextPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Context Viewer</h1>
        <p className="text-gray-400 mt-1">
          Browse schemas and semantic layer
        </p>
      </div>

      <Card className="bg-gray-900 border-gray-800">
        <CardHeader>
          <CardTitle className="text-white flex items-center gap-2">
            Schema Browser
            <Badge variant="secondary" className="bg-gray-800 text-gray-300">
              Coming Soon
            </Badge>
          </CardTitle>
          <CardDescription className="text-gray-400">
            Explore your database schema, view table relationships, and browse
            the semantic layer definitions.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-gray-500 text-sm">
            Select a connection to browse its schema and semantic context.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
