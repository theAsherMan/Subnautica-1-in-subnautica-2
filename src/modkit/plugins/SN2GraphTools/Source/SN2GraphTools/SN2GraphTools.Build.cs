using UnrealBuildTool;

public class SN2GraphTools : ModuleRules
{
	public SN2GraphTools(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
		PrivateDependencyModuleNames.AddRange(new string[] { "UnrealEd", "BlueprintGraph", "Kismet", "KismetCompiler", "UMG", "UMGEditor", "Slate", "SlateCore" });
	}
}
