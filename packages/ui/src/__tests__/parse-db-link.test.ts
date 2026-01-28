import { describe, it, expect } from "vitest";
import { parseDbLink } from "@/components/context/SchemaExplorer";

describe("parseDbLink", () => {
  it("parses full db:// link with all parts", () => {
    const result = parseDbLink("db://analytics/public/users/email");
    expect(result).toEqual({
      catalog: "analytics",
      schema: "public",
      table: "users",
      column: "email",
    });
  });

  it("parses link with catalog, schema, table", () => {
    const result = parseDbLink("db://analytics/public/orders");
    expect(result).toEqual({
      catalog: "analytics",
      schema: "public",
      table: "orders",
      column: null,
    });
  });

  it("parses link with catalog and schema only", () => {
    const result = parseDbLink("db://analytics/public");
    expect(result).toEqual({
      catalog: "analytics",
      schema: "public",
      table: null,
      column: null,
    });
  });

  it("parses link with catalog only", () => {
    const result = parseDbLink("db://analytics");
    expect(result).toEqual({
      catalog: "analytics",
      schema: null,
      table: null,
      column: null,
    });
  });

  it("returns null for non-db:// links", () => {
    expect(parseDbLink("https://example.com")).toBeNull();
    expect(parseDbLink("http://db://fake")).toBeNull();
    expect(parseDbLink("")).toBeNull();
    expect(parseDbLink("db//missing-colon")).toBeNull();
  });

  it("handles dotted names in parts", () => {
    const result = parseDbLink("db://my-catalog/my.schema/user.table");
    expect(result).toEqual({
      catalog: "my-catalog",
      schema: "my.schema",
      table: "user.table",
      column: null,
    });
  });
});
