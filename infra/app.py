import aws_cdk as cdk
from transcription_stack import TranscriptionAppStack

app = cdk.App()
TranscriptionAppStack(
    app, "TranscriptionAppStack",
    env=cdk.Environment(region="us-east-1"),
)
app.synth()
