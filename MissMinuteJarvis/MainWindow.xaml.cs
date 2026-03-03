using System;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Shapes;
using System.Windows.Threading;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Threading.Tasks;
using System.Speech.Synthesis;
using System.Runtime.InteropServices;

namespace MissMinuteJarvis
{
    public class Spring {
        public double Value; public double Velocity; public double Target;
        public double Stiffness = 0.06; public double Damping = 0.8;
        public void Update() { Velocity = (Velocity + (Target - Value) * Stiffness) * Damping; Value += Velocity; }
    }

    public partial class MainWindow : Window
    {
        [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] private static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);

        private double _t = 0;
        private SpeechSynthesizer? _synth;
        private Spring _winX = new Spring();
        private Spring _winY = new Spring();
        private Spring _tiltX = new Spring();
        private Spring _pupilX = new Spring();
        private Spring _pupilY = new Spring();
        private Random _rnd = new Random();
        private bool _isSpeaking = false;
        private double _nextRoamTime = 0;
        private int _blinkTimer = 0;

        public MainWindow()
        {
            InitializeComponent();
            _winX.Value = _winX.Target = SystemParameters.PrimaryScreenWidth - 620;
            _winY.Value = _winY.Target = SystemParameters.PrimaryScreenHeight - 620;
            DrawTicks();
            CompositionTarget.Rendering += OnRendering;
            SetupVoice();
            this.MouseDown += (s, e) => { if (e.LeftButton == MouseButtonState.Pressed) DragMove(); };
        }

        private void SetupVoice() {
            try {
                _synth = new SpeechSynthesizer();
                _synth.SelectVoiceByHints(VoiceGender.Female);
                _synth.Rate = 2;
                _synth.StateChanged += (s, e) => _isSpeaking = (e.State == SynthesizerState.Speaking);
            } catch { }
        }

        private void OnRendering(object? sender, EventArgs e) {
            _t += 0.08;
            
            if (_t > _nextRoamTime && !_isSpeaking) {
                _winX.Target = _rnd.Next(100, (int)SystemParameters.PrimaryScreenWidth - 550);
                _winY.Target = _rnd.Next(100, (int)SystemParameters.PrimaryScreenHeight - 550);
                _nextRoamTime = _t + _rnd.Next(100, 300) * 0.1;
                _pupilX.Target = (_winX.Target > _winX.Value) ? 14 : -14;
                _pupilY.Target = _rnd.Next(-10, 10);
            }

            _winX.Update(); _winY.Update();
            _tiltX.Target = Math.Clamp(_winX.Velocity * 0.6, -15, 15);
            _tiltX.Update(); _pupilX.Update(); _pupilY.Update();

            this.Left = _winX.Value; this.Top = _winY.Value;
            BodySkew.AngleX = _tiltX.Value;
            BodyTranslate.Y = Math.Sin(_t) * 15;

            _blinkTimer--;
            if (_blinkTimer <= 0) {
                if (LeftPupil.Opacity > 0) { LeftPupil.Opacity = RightPupil.Opacity = 0; _blinkTimer = 4; }
                else { LeftPupil.Opacity = RightPupil.Opacity = 1; _blinkTimer = _rnd.Next(40, 150); }
            }

            UpdateLimbs(_t); UpdateEyes(); UpdateHoloRings(_t); UpdateMouth(_t);
            
            if (_isSpeaking) CoreGlow.Opacity = 0.4 + Math.Sin(_t * 15) * 0.2;
            else CoreGlow.Opacity = 0.3 + Math.Sin(_t * 0.5) * 0.05;
        }

        private void UpdateLimbs(double t) {
            double cx = 300, cy = 300;
            double moveSpeed = Math.Sqrt(_winX.Velocity * _winX.Velocity + _winY.Velocity * _winY.Velocity);
            double walkCycle = t * (1.0 + moveSpeed * 0.1);
            double vx = _winX.Velocity * -2.0, vy = _winY.Velocity * -2.0;

            for (int i = 0; i < 2; i++) {
                int s = (i == 0) ? -1 : 1; 
                double p = walkCycle * 1.5 + (i * Math.PI);
                double bend = Math.Sin(p) * 20;
                Point p1 = new Point(cx + 70 * s, cy);
                Point p3 = new Point(cx + 140 * s + bend + vx, cy + 20 + bend * 0.5 + vy);
                var path = (i == 0) ? LeftArm : RightArm;
                var glove = (i == 0) ? LeftGlove : RightGlove;
                path.Data = Geometry.Parse(string.Format(CultureInfo.InvariantCulture, "M {0:F1},{1:F1} Q {2:F1},{3:F1} {4:F1},{5:F1}", p1.X, p1.Y, cx + 110 * s + bend + vx, cy + 40 + bend + vy, p3.X, p3.Y));
                Canvas.SetLeft(glove, p3.X-16); Canvas.SetTop(glove, p3.Y-16);

                double lp = walkCycle * 1.2 + (i * Math.PI * 0.8);
                double sw = Math.Sin(lp) * 15;
                Point l3 = new Point(cx + 60 * s + sw + vx, cy + 130 + Math.Abs(sw) + vy);
                var lPath = (i == 0) ? LeftLeg : RightLeg;
                var shoe = (i == 0) ? LeftShoe : RightShoe;
                lPath.Data = Geometry.Parse(string.Format(CultureInfo.InvariantCulture, "M {0:F1},{1:F1} Q {2:F1},{3:F1} {4:F1},{5:F1}", cx + 40 * s, cy + 75, cx + 50 * s + sw + vx, cy + 105 + vy, l3.X, l3.Y));
                Canvas.SetLeft(shoe, l3.X - 25); Canvas.SetTop(shoe, l3.Y - 14);
            }
        }

        private void UpdateEyes() {
            Canvas.SetLeft(LeftPupil, 260 + _pupilX.Value); Canvas.SetTop(LeftPupil, 270 + _pupilY.Value);
            Canvas.SetLeft(RightPupil, 324 + _pupilX.Value); Canvas.SetTop(RightPupil, 270 + _pupilY.Value);
        }

        private void UpdateHoloRings(double t) {
            Ring1.RenderTransform = new RotateTransform(t * 40, 160, 160);
            Ring2.RenderTransform = new RotateTransform(-t * 25, 180, 180);
        }

        private void UpdateMouth(double t) {
            double mY = 335 + (_isSpeaking ? Math.Abs(Math.Sin(t * 20) * 12) : Math.Sin(t * 2) * 2);
            MouthPath.Data = Geometry.Parse(string.Format(CultureInfo.InvariantCulture, "M 275,330 Q 300,{0:F1} 325,330", mY));
        }

        private void DrawTicks() {
            for (int i = 0; i < 12; i++) {
                double a = (Math.PI / 180) * (i * 30 - 90);
                TicksCanvas.Children.Add(new Line { X1 = 80 + Math.Cos(a) * 60, Y1 = 80 + Math.Sin(a) * 60, X2 = 80 + Math.Cos(a) * 72, Y2 = 80 + Math.Sin(a) * 72, Stroke = new SolidColorBrush(Color.FromRgb(33, 16, 7)), StrokeThickness = 4 });
            }
        }

        private void OpenDashboard_Click(object s, RoutedEventArgs e) => Process.Start(new ProcessStartInfo("http://localhost:8080") { UseShellExecute = true });
        private void Restart_Click(object s, RoutedEventArgs e) { Process.Start(Process.GetCurrentProcess()?.MainModule?.FileName ?? ""); Application.Current.Shutdown(); }
        private void ExitAll_Click(object s, RoutedEventArgs e) => Application.Current.Shutdown();
    }
}
