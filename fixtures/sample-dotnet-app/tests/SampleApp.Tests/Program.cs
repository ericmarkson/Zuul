using System.Xml;
using SampleApp;

var resultPath = GetArg(args, "--result") ?? "results.xml";
var calculator = new Calculator();
var results = new List<(string Name, bool Passed, string? Failure)>();

RunTest("Add_ReturnsSum", () =>
{
    var actual = calculator.Add(2, 3);
    Assert(actual == 5, $"expected 5, got {actual}");
});

RunTest("Subtract_ReturnsDifference", () =>
{
    var actual = calculator.Subtract(2, 3);
    Assert(actual == -1, $"expected -1, got {actual}");
});

RunTest("Divide_ByZero_ThrowsArgumentException", () =>
{
    try
    {
        calculator.Divide(10, 0);
        Assert(false, "expected ArgumentException, but Divide returned normally");
    }
    catch (ArgumentException)
    {
        // expected
    }
});

WriteJUnitXml(resultPath, results);

foreach (var r in results)
{
    Console.WriteLine(r.Passed ? $"PASS {r.Name}" : $"FAIL {r.Name}: {r.Failure}");
}

var failedCount = results.Count(r => !r.Passed);
Console.WriteLine(failedCount == 0 ? "All tests passed." : $"{failedCount} test(s) failed.");
Environment.Exit(failedCount == 0 ? 0 : 1);

void RunTest(string name, Action body)
{
    try
    {
        body();
        results.Add((name, true, null));
    }
    catch (Exception ex)
    {
        results.Add((name, false, ex.Message));
    }
}

void Assert(bool condition, string message)
{
    if (!condition) throw new Exception(message);
}

string? GetArg(string[] a, string flag)
{
    var idx = Array.IndexOf(a, flag);
    return idx >= 0 && idx + 1 < a.Length ? a[idx + 1] : null;
}

void WriteJUnitXml(string path, List<(string Name, bool Passed, string? Failure)> testResults)
{
    var dir = Path.GetDirectoryName(Path.GetFullPath(path));
    if (!string.IsNullOrEmpty(dir))
    {
        Directory.CreateDirectory(dir);
    }

    var doc = new XmlDocument();
    var suite = doc.CreateElement("testsuite");
    suite.SetAttribute("name", "SampleApp.Tests");
    suite.SetAttribute("tests", testResults.Count.ToString());
    suite.SetAttribute("failures", testResults.Count(r => !r.Passed).ToString());
    doc.AppendChild(suite);

    foreach (var r in testResults)
    {
        var testcase = doc.CreateElement("testcase");
        testcase.SetAttribute("name", r.Name);
        testcase.SetAttribute("classname", "SampleApp.Tests");
        if (!r.Passed)
        {
            var failure = doc.CreateElement("failure");
            failure.SetAttribute("message", r.Failure ?? "assertion failed");
            testcase.AppendChild(failure);
        }
        suite.AppendChild(testcase);
    }

    doc.Save(path);
}
