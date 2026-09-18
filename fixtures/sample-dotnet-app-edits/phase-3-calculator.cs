namespace SampleApp;

public class Calculator
{
    public double Add(double a, double b) => a + b;

    public double Sub(double a, double b) => a - b;

    public double Multiply(double a, double b) => a * b;

    public double Divide(double a, double b)
    {
        if (b == 0)
        {
            throw new ArgumentException("Divisor cannot be zero.", nameof(b));
        }

        return a / b;
    }
}
